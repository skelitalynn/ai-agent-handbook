from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from durable_workflow import (
    DefinitionError,
    IdempotentEffectStore,
    InjectedCrash,
    InvalidTransition,
    PermanentActivityError,
    RetryableActivityError,
    RunStatus,
    SQLiteEventStore,
    Step,
    VersionConflict,
    VersionMismatch,
    WorkflowDefinition,
    WorkflowEngine,
)


def return_name(name: str):
    def activity(_context, operation_id):
        return {"name": name, "operation_id": operation_id}

    return activity


class DurableWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.event_path = root / "events.sqlite3"
        self.effect_path = root / "effects.sqlite3"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def engine(self, definition: WorkflowDefinition) -> WorkflowEngine:
        return WorkflowEngine(definition, SQLiteEventStore(self.event_path))

    def test_completed_state_is_rebuilt_after_process_restart(self) -> None:
        definition = WorkflowDefinition(
            "v1",
            [Step("first", return_name("first")), Step("second", return_name("second"))],
        )
        state = self.engine(definition).start("run-1", {"topic": "agents"})
        self.assertEqual(RunStatus.COMPLETED, state.status)
        self.assertEqual(["first", "second"], state.completed_steps)

        rebuilt = self.engine(definition).get_state("run-1")
        self.assertEqual(state.outputs, rebuilt.outputs)
        self.assertEqual(state.seq, rebuilt.seq)

    def test_approval_can_resume_with_a_new_engine_instance(self) -> None:
        definition = WorkflowDefinition(
            "v1",
            [Step("publish", return_name("publish"), approval_prompt="Publish?")],
        )
        paused = self.engine(definition).start("run-2", {})
        self.assertEqual(RunStatus.PAUSED, paused.status)

        restarted = self.engine(definition)
        restarted.decide_approval("run-2", approved=True, actor="reviewer")
        completed = restarted.advance("run-2")
        self.assertEqual(RunStatus.COMPLETED, completed.status)
        self.assertTrue(completed.approvals["publish"])

    def test_rejected_approval_compensates_in_reverse_order(self) -> None:
        compensation_order: list[str] = []

        def compensate(name: str):
            def activity(_context, _operation_id):
                compensation_order.append(name)
                return {"compensated": name}

            return activity

        definition = WorkflowDefinition(
            "v1",
            [
                Step("a", return_name("a"), compensate=compensate("a")),
                Step("b", return_name("b"), compensate=compensate("b")),
                Step("dangerous", return_name("dangerous"), approval_prompt="Proceed?"),
            ],
        )
        engine = self.engine(definition)
        paused = engine.start("run-3", {})
        self.assertEqual(RunStatus.PAUSED, paused.status)
        engine.decide_approval("run-3", approved=False, actor="reviewer")
        cancelled = engine.advance("run-3")

        self.assertEqual(RunStatus.CANCELLED, cancelled.status)
        self.assertEqual(["b", "a"], compensation_order)
        self.assertEqual(["b", "a"], cancelled.compensated_steps)

    def test_retryable_failure_uses_a_bounded_attempt_budget(self) -> None:
        calls = 0

        def flaky(_context, _operation_id):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RetryableActivityError("temporary outage")
            return {"ok": True}

        definition = WorkflowDefinition("v1", [Step("flaky", flaky, max_attempts=2)])
        state = self.engine(definition).start("run-4", {})
        self.assertEqual(RunStatus.COMPLETED, state.status)
        self.assertEqual(2, state.attempts["flaky"])

    def test_permanent_failure_triggers_compensation(self) -> None:
        compensation_order: list[str] = []

        def compensate(_context, _operation_id):
            compensation_order.append("prepared")
            return {"ok": True}

        def fail(_context, _operation_id):
            raise PermanentActivityError("invalid account")

        definition = WorkflowDefinition(
            "v1",
            [
                Step("prepare", return_name("prepare"), compensate=compensate),
                Step("commit", fail),
            ],
        )
        state = self.engine(definition).start("run-5", {})
        self.assertEqual(RunStatus.FAILED, state.status)
        self.assertEqual(["prepared"], compensation_order)

    def test_crash_after_effect_is_safe_when_target_deduplicates(self) -> None:
        effects = IdempotentEffectStore(self.effect_path)
        invocations = 0

        def create_record(_context, operation_id):
            nonlocal invocations
            invocations += 1
            return effects.apply(operation_id, "create_record", {"value": 7})

        definition = WorkflowDefinition("v1", [Step("create", create_record)])
        engine = self.engine(definition)
        with self.assertRaises(InjectedCrash):
            engine.start("run-6", {}, crash_after_effect="create")

        completed = self.engine(definition).advance("run-6")
        self.assertEqual(RunStatus.COMPLETED, completed.status)
        self.assertEqual(2, invocations)
        self.assertEqual(1, effects.count())
        self.assertEqual(2, completed.attempts["create"])

    def test_cancel_compensates_completed_steps(self) -> None:
        compensated: list[str] = []

        def undo(_context, _operation_id):
            compensated.append("prepare")
            return {"ok": True}

        definition = WorkflowDefinition(
            "v1",
            [
                Step("prepare", return_name("prepare"), compensate=undo),
                Step("approve", return_name("approve"), approval_prompt="Continue?"),
            ],
        )
        engine = self.engine(definition)
        paused = engine.start("run-7", {})
        self.assertEqual(RunStatus.PAUSED, paused.status)
        cancelled = engine.cancel("run-7", "user requested cancellation")
        self.assertEqual(RunStatus.CANCELLED, cancelled.status)
        self.assertEqual(["prepare"], compensated)

    def test_compensation_failure_is_visible_and_not_reported_as_rollback(self) -> None:
        def cannot_undo(_context, _operation_id):
            raise PermanentActivityError("manual repair required")

        def fail(_context, _operation_id):
            raise PermanentActivityError("commit failed")

        definition = WorkflowDefinition(
            "v1",
            [
                Step("prepare", return_name("prepare"), compensate=cannot_undo),
                Step("commit", fail),
            ],
        )
        state = self.engine(definition).start("run-8", {})
        self.assertEqual(RunStatus.COMPENSATION_FAILED, state.status)
        self.assertIn("manual repair required", state.reason)

    def test_stale_writer_is_rejected_by_optimistic_concurrency(self) -> None:
        store = SQLiteEventStore(self.event_path)
        store.append("run-9", 0, "RunStarted", {"definition_version": "v1", "input": {}})
        store.append("run-9", 1, "RunCompleted", {"output": {}})
        with self.assertRaises(VersionConflict):
            store.append("run-9", 1, "RunCancelled", {"reason": "stale writer"})

    def test_definition_version_is_checked_before_resume(self) -> None:
        old_definition = WorkflowDefinition(
            "v1",
            [Step("approval", return_name("approval"), approval_prompt="Continue?")],
        )
        self.engine(old_definition).start("run-10", {})

        new_definition = WorkflowDefinition(
            "v2",
            [Step("approval", return_name("approval"), approval_prompt="Continue?")],
        )
        with self.assertRaises(VersionMismatch):
            self.engine(new_definition).get_state("run-10")

    def test_duplicate_step_names_are_rejected(self) -> None:
        with self.assertRaises(DefinitionError):
            WorkflowDefinition(
                "v1",
                [Step("same", return_name("a")), Step("same", return_name("b"))],
            )

    def test_idempotency_key_cannot_be_reused_for_different_intent(self) -> None:
        effects = IdempotentEffectStore(self.effect_path)
        effects.apply("op-1", "charge", {"amount": 10})
        with self.assertRaises(InvalidTransition):
            effects.apply("op-1", "charge", {"amount": 20})


if __name__ == "__main__":
    unittest.main()
