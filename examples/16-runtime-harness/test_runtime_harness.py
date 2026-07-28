import dataclasses
import unittest

from runtime_harness import (
    ArtifactStore,
    FinalAnswer,
    Harness,
    Mount,
    Pause,
    RunState,
    RunStatus,
    RuntimePolicy,
    RuntimeViolation,
    ToolCall,
    ToolResult,
    Workspace,
)


def workspace():
    return Workspace(
        (Mount("inputs", True), Mount("work", False), Mount("outputs", False)),
        {"inputs/request.txt": "hello"},
    )


class RuntimeHarnessTests(unittest.TestCase):
    def make_harness(self, model, tools=None, **kwargs):
        return Harness(
            model=model,
            tools=tools or {},
            policy=kwargs.pop("policy", RuntimePolicy(frozenset(tools or {}))),
            workspace=kwargs.pop("workspace", workspace()),
            artifacts=kwargs.pop("artifacts", ArtifactStore()),
            observers=kwargs.pop("observers", ()),
            local_context=kwargs.pop("local_context", {}),
            **kwargs,
        )

    def test_runtime_emits_ordered_model_lifecycle(self):
        runtime = self.make_harness(lambda _request: FinalAnswer("done")).runtime()
        state = runtime.run(runtime.new_state("run-1", "finish"))
        self.assertEqual(state.status, RunStatus.COMPLETED)
        self.assertEqual(
            [event.kind for event in runtime.events],
            ["run.started", "model.started", "model.completed", "run.completed"],
        )
        self.assertEqual([event.sequence for event in runtime.events], [1, 2, 3, 4])

    def test_runtime_policy_blocks_unlisted_tool_before_execution(self):
        called = False

        def dangerous(_context, _arguments):
            nonlocal called
            called = True
            return ToolResult("bad")

        harness = self.make_harness(
            lambda _request: ToolCall("shell"),
            {"shell": dangerous},
            policy=RuntimePolicy(frozenset()),
        )
        state = harness.runtime().run(harness.runtime().new_state("run-1", "x"))
        self.assertEqual(state.status, RunStatus.FAILED)
        self.assertFalse(called)

    def test_model_step_budget_stops_an_endless_loop(self):
        def noop(_context, _arguments):
            return ToolResult("again")

        harness = self.make_harness(
            lambda _request: ToolCall("noop"),
            {"noop": noop},
            policy=RuntimePolicy(frozenset({"noop"}), max_steps=2, max_tool_calls=5),
        )
        runtime = harness.runtime()
        state = runtime.run(runtime.new_state("run-1", "loop"))
        self.assertEqual(state.status, RunStatus.FAILED)
        self.assertIn("maximum model steps", state.error)

    def test_cancel_before_start_prevents_model_call(self):
        called = False

        def model(_request):
            nonlocal called
            called = True
            return FinalAnswer("done")

        runtime = self.make_harness(model).runtime()
        state = runtime.new_state("run-1", "x")
        runtime.cancel(state)
        runtime.run(state)
        self.assertEqual(state.status, RunStatus.CANCELLED)
        self.assertFalse(called)

    def test_workspace_rejects_traversal_and_unknown_mounts(self):
        ws = workspace()
        with self.assertRaises(RuntimeViolation):
            ws.write("work/../../secret.txt", "x")
        with self.assertRaises(RuntimeViolation):
            ws.write("outside/file.txt", "x")

    def test_workspace_enforces_read_only_mount(self):
        with self.assertRaisesRegex(RuntimeViolation, "read-only"):
            workspace().write("inputs/request.txt", "changed")

    def test_local_context_is_available_to_tools_not_model(self):
        seen = {}

        def model(request):
            seen["request"] = request
            return ToolCall("lookup") if request.step == 1 else FinalAnswer(request.observations[-1])

        def lookup(context, _arguments):
            return ToolResult(f"used:{context.require('api_key')}")

        harness = self.make_harness(
            model,
            {"lookup": lookup},
            local_context={"api_key": "secret"},
        )
        state = harness.runtime().run(harness.runtime().new_state("run-1", "x"))
        self.assertEqual(state.final_answer, "used:secret")
        self.assertFalse(hasattr(seen["request"], "local_context"))

    def test_tool_can_publish_a_versioned_artifact(self):
        artifacts = ArtifactStore()

        def model(request):
            return ToolCall("write") if request.step == 1 else FinalAnswer("done")

        def write(context, _arguments):
            context.workspace.write("outputs/report.txt", "report-v1")
            return ToolResult("written", ("outputs/report.txt",))

        harness = self.make_harness(model, {"write": write}, artifacts=artifacts)
        state = harness.runtime().run(harness.runtime().new_state("run-1", "x"))
        artifact = artifacts.get(state.artifact_ids[0])
        self.assertEqual(artifact.content, "report-v1")
        self.assertEqual(len(artifact.sha256), 64)

    def test_same_content_at_different_paths_has_distinct_artifact_identity(self):
        artifacts = ArtifactStore()
        first = artifacts.publish("run-1", "outputs/a.txt", "same", 1)
        second = artifacts.publish("run-1", "outputs/b.txt", "same", 1)
        self.assertNotEqual(first.artifact_id, second.artifact_id)
        self.assertEqual(first.sha256, second.sha256)

    def test_runtime_rejects_artifact_outside_publish_mount(self):
        def write(context, _arguments):
            context.workspace.write("work/draft.txt", "draft")
            return ToolResult("written", ("work/draft.txt",))

        harness = self.make_harness(lambda _request: ToolCall("write"), {"write": write})
        state = harness.runtime().run(harness.runtime().new_state("run-1", "x"))
        self.assertEqual(state.status, RunStatus.FAILED)
        self.assertIn("outside publish mount", state.error)

    def test_pause_state_survives_json_and_resumes(self):
        def model(request):
            return Pause("approval") if request.step == 1 else FinalAnswer("approved")

        harness = self.make_harness(model)
        first_runtime = harness.runtime()
        paused = first_runtime.run(first_runtime.new_state("run-1", "x"))
        restored = RunState.from_json(paused.to_json())
        second_runtime = harness.runtime()
        completed = second_runtime.run(restored)
        self.assertEqual(completed.status, RunStatus.COMPLETED)
        self.assertEqual(second_runtime.events[0].kind, "run.resumed")

    def test_observer_failure_is_recorded_without_changing_run_result(self):
        def broken(_event):
            raise RuntimeError("observer down")

        runtime = self.make_harness(
            lambda _request: FinalAnswer("done"), observers=(broken,)
        ).runtime()
        state = runtime.run(runtime.new_state("run-1", "x"))
        self.assertEqual(state.status, RunStatus.COMPLETED)
        self.assertTrue(runtime.observer_errors)

    def test_events_are_immutable_observations_not_policy_objects(self):
        seen = []

        def observer(event):
            seen.append(event)

        runtime = self.make_harness(
            lambda _request: FinalAnswer("done"), observers=(observer,)
        ).runtime()
        runtime.run(runtime.new_state("run-1", "x"))
        with self.assertRaises(TypeError):
            seen[0].data["authorized"] = True
        with self.assertRaises(dataclasses.FrozenInstanceError):
            seen[0].kind = "tool.allowed"


if __name__ == "__main__":
    unittest.main()
