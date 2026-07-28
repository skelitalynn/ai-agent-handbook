import unittest

from multi_agent_orchestrator import (
    AgentSpec,
    Coordinator,
    PlanError,
    TaskSpec,
    TaskStatus,
    WorkerResult,
)


def constant_worker(request):
    return WorkerResult(
        summary=f"finished {request.task_id}",
        artifacts={name: f"{request.task_id}:{name}" for name in ("result",)},
        token_usage=10,
        tool_calls=tuple(sorted(request.allowed_tools)),
    )


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.agents = [
            AgentSpec("broad", frozenset({"research", "write"}), frozenset({"web", "files"})),
            AgentSpec("researcher", frozenset({"research"}), frozenset({"web"})),
            AgentSpec("writer", frozenset({"write"}), frozenset()),
        ]
        self.workers = {agent.name: constant_worker for agent in self.agents}

    def coordinator(self, **kwargs):
        return Coordinator(self.agents, self.workers, **kwargs)

    def test_selects_the_least_privileged_qualified_agent(self):
        report = self.coordinator().run(
            "run-1",
            [TaskSpec("r", "research", "research", requested_tools=frozenset({"web"}))],
        )
        self.assertEqual(report.records["r"].agent_name, "researcher")

    def test_rejects_a_task_without_a_qualified_agent(self):
        with self.assertRaisesRegex(PlanError, "no agent can satisfy"):
            self.coordinator().run(
                "run-1",
                [TaskSpec("pay", "pay", "finance", requested_tools=frozenset({"bank"}))],
            )

    def test_rejects_duplicate_task_ids(self):
        tasks = [TaskSpec("same", "a", "write"), TaskSpec("same", "b", "write")]
        with self.assertRaisesRegex(PlanError, "unique"):
            self.coordinator().run("run-1", tasks)

    def test_rejects_dependency_cycles(self):
        tasks = [
            TaskSpec("a", "a", "write", depends_on=("b",)),
            TaskSpec("b", "b", "write", depends_on=("a",)),
        ]
        with self.assertRaisesRegex(PlanError, "cycle"):
            self.coordinator().run("run-1", tasks)

    def test_independent_tasks_share_a_parallel_batch(self):
        tasks = [
            TaskSpec("a", "a", "research"),
            TaskSpec("b", "b", "write"),
        ]
        report = self.coordinator(max_parallel=2).run("run-1", tasks)
        self.assertEqual(report.batches[0], ("a", "b"))

    def test_tasks_with_overlapping_writes_are_serialized(self):
        tasks = [
            TaskSpec("a", "a", "write", write_keys=frozenset({"report"})),
            TaskSpec("b", "b", "write", write_keys=frozenset({"report"})),
        ]
        report = self.coordinator(max_parallel=2).run("run-1", tasks)
        self.assertEqual(report.batches, (("a",), ("b",)))

    def test_worker_receives_only_dependency_artifacts(self):
        seen = {}

        def capture(request):
            seen[request.task_id] = tuple(sorted(request.input_artifacts))
            return WorkerResult("ok", {"result": request.task_id}, token_usage=1)

        workers = {agent.name: capture for agent in self.agents}
        tasks = [
            TaskSpec("source", "source", "research", expected_outputs=frozenset({"result"})),
            TaskSpec("unrelated", "other", "write", expected_outputs=frozenset({"result"})),
            TaskSpec(
                "consumer",
                "consume",
                "write",
                depends_on=("source",),
                expected_outputs=frozenset({"result"}),
            ),
        ]
        Coordinator(self.agents, workers).run("run-1", tasks)
        self.assertEqual(seen["consumer"], ("source:result",))

    def test_worker_cannot_report_an_unauthorized_tool(self):
        def unsafe(_request):
            return WorkerResult("no", token_usage=1, tool_calls=("shell",))

        workers = dict(self.workers)
        workers["writer"] = unsafe
        report = Coordinator(self.agents, workers).run(
            "run-1", [TaskSpec("w", "write", "write")]
        )
        self.assertEqual(report.records["w"].status, TaskStatus.FAILED)
        self.assertIn("unauthorized", report.records["w"].error)

    def test_missing_contract_output_fails_and_skips_dependant(self):
        tasks = [
            TaskSpec("a", "a", "write", expected_outputs=frozenset({"draft"})),
            TaskSpec("b", "b", "write", depends_on=("a",)),
        ]
        report = self.coordinator().run("run-1", tasks)
        self.assertEqual(report.records["a"].status, TaskStatus.FAILED)
        self.assertEqual(report.records["b"].status, TaskStatus.SKIPPED)

    def test_failed_branch_does_not_cancel_an_independent_branch(self):
        def sometimes_fails(request):
            if request.task_id == "bad":
                raise RuntimeError("boom")
            return WorkerResult("ok", token_usage=1)

        workers = {agent.name: sometimes_fails for agent in self.agents}
        tasks = [TaskSpec("bad", "bad", "write"), TaskSpec("good", "good", "research")]
        report = Coordinator(self.agents, workers).run("run-1", tasks)
        self.assertEqual(report.records["bad"].status, TaskStatus.FAILED)
        self.assertEqual(report.records["good"].status, TaskStatus.SUCCEEDED)

    def test_worker_token_overrun_is_rejected(self):
        def expensive(_request):
            return WorkerResult("too much", token_usage=11)

        workers = dict(self.workers)
        workers["writer"] = expensive
        report = Coordinator(self.agents, workers).run(
            "run-1", [TaskSpec("w", "write", "write", max_tokens=10)]
        )
        self.assertEqual(report.records["w"].status, TaskStatus.FAILED)
        self.assertIn("token budget", report.records["w"].error)

    def test_run_budget_limits_parallel_admission(self):
        tasks = [
            TaskSpec("a", "a", "write", max_tokens=60),
            TaskSpec("b", "b", "research", max_tokens=60),
        ]
        report = self.coordinator(max_parallel=2, total_token_budget=100).run("run-1", tasks)
        self.assertEqual(report.batches, (("a",), ("b",)))
        self.assertTrue(report.succeeded)

    def test_artifacts_are_namespaced_by_source_task(self):
        tasks = [
            TaskSpec("a", "a", "write", expected_outputs=frozenset({"result"})),
            TaskSpec("b", "b", "research", expected_outputs=frozenset({"result"})),
        ]
        report = self.coordinator().run("run-1", tasks)
        self.assertEqual(set(report.artifacts), {"a:result", "b:result"})


if __name__ == "__main__":
    unittest.main()
