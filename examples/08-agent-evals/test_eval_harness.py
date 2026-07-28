import unittest

from eval_harness import (
    BudgetGrader,
    EvalTask,
    Event,
    OutcomeGrader,
    ToolExpectation,
    ToolPolicyGrader,
    Trial,
    run_suite,
)


def trial(
    *,
    outcome: str = "done",
    events: tuple[Event, ...] = (),
    cost: float = 0.01,
) -> Trial:
    return Trial("claimed success", {"status": outcome}, events, cost)


class GraderTests(unittest.TestCase):
    def test_outcome_uses_environment_state_not_final_claim(self) -> None:
        task = EvalTask("t", "do it", {"status": "done"})
        grade = OutcomeGrader().grade(task, trial(outcome="pending"))
        self.assertFalse(grade.passed)

    def test_required_tool_arguments_are_checked(self) -> None:
        task = EvalTask(
            "t",
            "do it",
            {"status": "done"},
            required_calls=(ToolExpectation("cancel", {"id": "A-17"}),),
        )
        wrong = trial(events=(Event("tool_call", "cancel", {"id": "B-9"}),))
        self.assertFalse(ToolPolicyGrader().grade(task, wrong).passed)

    def test_forbidden_tool_fails_even_when_outcome_is_correct(self) -> None:
        task = EvalTask(
            "t", "do it", {"status": "done"}, forbidden_tools=("refund",)
        )
        result = trial(events=(Event("tool_call", "refund", {"amount": 10}),))
        self.assertFalse(ToolPolicyGrader().grade(task, result).passed)
        self.assertTrue(OutcomeGrader().grade(task, result).passed)

    def test_budget_checks_steps_and_cost(self) -> None:
        task = EvalTask("t", "do it", {}, max_steps=1, max_cost=0.02)
        too_many_steps = trial(
            events=(Event("model", "a", {}), Event("model", "b", {}))
        )
        too_expensive = trial(cost=0.03)
        self.assertFalse(BudgetGrader().grade(task, too_many_steps).passed)
        self.assertFalse(BudgetGrader().grade(task, too_expensive).passed)


class SuiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tasks = [
            EvalTask("a", "A", {"status": "done"}, tags=("core",)),
            EvalTask("b", "B", {"status": "done"}, tags=("edge",)),
        ]

    def test_any_and_all_trial_metrics_diverge(self) -> None:
        def runner(task: EvalTask, attempt: int) -> Trial:
            if task.task_id == "a":
                return trial(outcome="done")
            return trial(outcome="done" if attempt == 0 else "failed")

        report = run_suite(
            self.tasks, runner, [OutcomeGrader()], trials_per_task=2
        )
        self.assertEqual(report.trial_success_rate, 0.75)
        self.assertEqual(report.pass_at_k, 1.0)
        self.assertEqual(report.pass_pow_k, 0.5)

    def test_all_graders_must_pass_a_trial(self) -> None:
        task = EvalTask(
            "a", "A", {"status": "done"}, forbidden_tools=("delete",)
        )

        def runner(_task: EvalTask, _attempt: int) -> Trial:
            return trial(events=(Event("tool_call", "delete", {}),))

        report = run_suite(
            [task], runner, [OutcomeGrader(), ToolPolicyGrader()], trials_per_task=1
        )
        self.assertEqual(report.trial_success_rate, 0.0)

    def test_tag_rates_are_aggregated(self) -> None:
        def runner(task: EvalTask, _attempt: int) -> Trial:
            return trial(outcome="done" if task.task_id == "a" else "failed")

        report = run_suite(
            self.tasks, runner, [OutcomeGrader()], trials_per_task=1
        )
        self.assertEqual(report.tag_success_rates, {"core": 1.0, "edge": 0.0})

    def test_duplicate_task_ids_are_rejected(self) -> None:
        duplicate = [
            EvalTask("same", "A", {}),
            EvalTask("same", "B", {}),
        ]
        with self.assertRaises(ValueError):
            run_suite(duplicate, lambda _task, _attempt: trial(), [], trials_per_task=1)

    def test_empty_suite_and_invalid_trial_count_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_suite([], lambda _task, _attempt: trial(), [], trials_per_task=1)
        with self.assertRaises(ValueError):
            run_suite(self.tasks, lambda _task, _attempt: trial(), [], trials_per_task=0)


if __name__ == "__main__":
    unittest.main()
