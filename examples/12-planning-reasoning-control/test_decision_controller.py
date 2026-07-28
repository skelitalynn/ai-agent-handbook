import unittest

from decision_controller import (
    Action,
    ControlLimits,
    Decision,
    DecisionController,
    Observation,
    PlanStep,
    PlanValidationError,
)


def act(step_id: str, name: str = "inspect", **kwargs) -> Decision:
    return Decision(
        kind="act",
        step_id=step_id,
        action=Action(name=name, **kwargs),
        observable_basis=f"step {step_id} is ready",
    )


def success(_: Action) -> Observation:
    return Observation(success=True, summary="verified", actual_cost=1.0)


def accept(_, observation: Observation) -> bool:
    return observation.summary == "verified"


class PlanValidationTests(unittest.TestCase):
    def test_dependency_cycle_is_rejected(self) -> None:
        plan = (
            PlanStep("a", "A", depends_on=("b",)),
            PlanStep("b", "B", depends_on=("a",)),
        )
        with self.assertRaises(PlanValidationError):
            DecisionController.validate_plan(plan)

    def test_unknown_dependency_is_rejected(self) -> None:
        with self.assertRaises(PlanValidationError):
            DecisionController.validate_plan((PlanStep("a", "A", ("missing",)),))


class ControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = (
            PlanStep("inspect", "Inspect inputs"),
            PlanStep("change", "Apply change", depends_on=("inspect",)),
        )
        self.controller = DecisionController(allowed_actions={"inspect", "change", "delete"})

    def test_successful_plan_requires_verified_steps_before_finish(self) -> None:
        decisions = iter(
            [
                act("inspect"),
                act("change", name="change"),
                Decision("finish", "all plan steps passed", message="done"),
            ]
        )
        result = self.controller.run(
            objective="make a safe change",
            initial_plan=self.plan,
            decide=lambda _: next(decisions),
            execute=success,
            evaluate=accept,
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual([step.status for step in result.plan], ["completed", "completed"])
        self.assertEqual(result.cost_used, 2.0)

    def test_dependency_order_is_enforced_by_runtime(self) -> None:
        result = self.controller.run(
            objective="change",
            initial_plan=self.plan,
            decide=lambda _: act("change", name="change"),
            execute=success,
            evaluate=accept,
        )
        self.assertEqual(result.status, "control_error")
        self.assertIn("dependencies", result.message)

    def test_finish_claim_is_rejected_while_steps_are_pending(self) -> None:
        result = self.controller.run(
            objective="change",
            initial_plan=self.plan,
            decide=lambda _: Decision("finish", "looks done", message="done"),
            execute=success,
            evaluate=accept,
        )
        self.assertEqual(result.status, "control_error")

    def test_high_risk_action_pauses_before_execution(self) -> None:
        executed = []
        result = self.controller.run(
            objective="delete data",
            initial_plan=(PlanStep("delete", "Delete data"),),
            decide=lambda _: act(
                "delete", name="delete", risk="high", estimated_cost=1.0
            ),
            execute=lambda action: executed.append(action) or success(action),
            evaluate=accept,
        )
        self.assertEqual(result.status, "needs_approval")
        self.assertEqual(executed, [])

    def test_repeated_equivalent_action_stops_loop(self) -> None:
        controller = DecisionController(
            allowed_actions={"inspect"},
            limits=ControlLimits(repeated_action_limit=2),
        )
        result = controller.run(
            objective="inspect",
            initial_plan=(PlanStep("inspect", "Inspect"),),
            decide=lambda _: act("inspect"),
            execute=lambda _: Observation(False, "same failure", retryable=True),
            evaluate=accept,
        )
        self.assertEqual(result.status, "loop_detected")
        self.assertEqual(sum(event.observation is not None for event in result.trace), 2)

    def test_estimated_cost_stops_action_before_execution(self) -> None:
        controller = DecisionController(
            allowed_actions={"inspect"},
            limits=ControlLimits(max_cost=0.5),
        )
        executed = []
        result = controller.run(
            objective="inspect",
            initial_plan=(PlanStep("inspect", "Inspect"),),
            decide=lambda _: act("inspect", estimated_cost=1.0),
            execute=lambda action: executed.append(action) or success(action),
            evaluate=accept,
        )
        self.assertEqual(result.status, "budget_exhausted")
        self.assertEqual(executed, [])

    def test_replan_after_failure_can_recover(self) -> None:
        decisions = iter(
            [
                act("inspect"),
                Decision(
                    "replan",
                    "primary source unavailable",
                    replacement_plan=(PlanStep("fallback", "Use fallback"),),
                ),
                act("fallback"),
                Decision("finish", "fallback verified", message="done"),
            ]
        )
        observations = iter(
            [
                Observation(False, "not found", retryable=False),
                Observation(True, "verified", actual_cost=1.0),
            ]
        )
        controller = DecisionController(allowed_actions={"inspect"})
        result = controller.run(
            objective="find evidence",
            initial_plan=(PlanStep("inspect", "Inspect"),),
            decide=lambda _: next(decisions),
            execute=lambda _: next(observations),
            evaluate=accept,
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.plan[0].step_id, "fallback")
        self.assertEqual(result.plan[0].status, "completed")

    def test_ask_returns_structured_pause(self) -> None:
        result = self.controller.run(
            objective="book travel",
            initial_plan=(PlanStep("book", "Book"),),
            decide=lambda _: Decision(
                "ask",
                "destination is missing",
                message="Which city should I book?",
            ),
            execute=success,
            evaluate=accept,
        )
        self.assertEqual(result.status, "needs_input")
        self.assertIn("city", result.message)

    def test_decision_budget_is_a_hard_loss_limit(self) -> None:
        controller = DecisionController(
            allowed_actions={"inspect"},
            limits=ControlLimits(max_decisions=2),
        )
        result = controller.run(
            objective="inspect",
            initial_plan=(PlanStep("inspect", "Inspect"),),
            decide=lambda _: Decision(
                "replan",
                "new attempt",
                replacement_plan=(PlanStep("inspect", "Inspect"),),
            ),
            execute=success,
            evaluate=accept,
        )
        self.assertEqual(result.status, "budget_exhausted")
        self.assertEqual(len(result.trace), 2)


if __name__ == "__main__":
    unittest.main()
