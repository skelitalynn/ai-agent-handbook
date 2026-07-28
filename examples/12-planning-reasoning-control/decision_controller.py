"""Deterministic outer control for model-proposed decisions.

The planner supplies structured, observable decisions.  It is never asked to expose
private chain-of-thought.  The controller validates dependencies, permissions,
budgets, repeated actions, completion claims, and high-risk approval boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Literal, Mapping, Sequence


StepStatus = Literal["pending", "completed", "failed"]
DecisionKind = Literal["act", "replan", "ask", "finish", "escalate"]
RunStatus = Literal[
    "completed",
    "needs_input",
    "needs_approval",
    "escalated",
    "budget_exhausted",
    "loop_detected",
    "control_error",
]


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    description: str
    depends_on: tuple[str, ...] = ()
    status: StepStatus = "pending"


@dataclass(frozen=True)
class Action:
    name: str
    arguments: tuple[tuple[str, str], ...] = ()
    estimated_cost: float = 0.0
    risk: Literal["low", "high"] = "low"

    @property
    def signature(self) -> tuple[str, tuple[tuple[str, str], ...]]:
        return self.name, tuple(sorted(self.arguments))


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    observable_basis: str
    step_id: str | None = None
    action: Action | None = None
    replacement_plan: tuple[PlanStep, ...] = ()
    message: str | None = None


@dataclass(frozen=True)
class Observation:
    success: bool
    summary: str
    actual_cost: float = 0.0
    retryable: bool = False


@dataclass(frozen=True)
class TraceEvent:
    decision: Decision
    observation: Observation | None = None
    accepted: bool | None = None


@dataclass(frozen=True)
class ControllerSnapshot:
    objective: str
    plan: tuple[PlanStep, ...]
    trace: tuple[TraceEvent, ...]
    decisions_used: int
    tool_calls_used: int
    cost_used: float


@dataclass(frozen=True)
class ControlLimits:
    max_decisions: int = 12
    max_tool_calls: int = 8
    max_cost: float = 10.0
    repeated_action_limit: int = 2


@dataclass(frozen=True)
class RunResult:
    status: RunStatus
    message: str
    plan: tuple[PlanStep, ...]
    trace: tuple[TraceEvent, ...]
    cost_used: float


Decider = Callable[[ControllerSnapshot], Decision]
Executor = Callable[[Action], Observation]
Evaluator = Callable[[PlanStep, Observation], bool]


class PlanValidationError(ValueError):
    pass


class DecisionController:
    def __init__(
        self,
        *,
        allowed_actions: set[str],
        limits: ControlLimits | None = None,
    ) -> None:
        self._allowed_actions = frozenset(allowed_actions)
        self._limits = limits or ControlLimits()
        if self._limits.max_decisions <= 0 or self._limits.max_tool_calls <= 0:
            raise ValueError("decision and tool-call limits must be positive")
        if self._limits.max_cost < 0 or self._limits.repeated_action_limit <= 0:
            raise ValueError("cost and repetition limits are invalid")

    def run(
        self,
        *,
        objective: str,
        initial_plan: Sequence[PlanStep],
        decide: Decider,
        execute: Executor,
        evaluate: Evaluator,
    ) -> RunResult:
        plan = tuple(initial_plan)
        self.validate_plan(plan)
        trace: list[TraceEvent] = []
        action_counts: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
        tool_calls = 0
        cost_used = 0.0

        for decision_number in range(1, self._limits.max_decisions + 1):
            snapshot = ControllerSnapshot(
                objective=objective,
                plan=plan,
                trace=tuple(trace),
                decisions_used=decision_number - 1,
                tool_calls_used=tool_calls,
                cost_used=cost_used,
            )
            decision = decide(snapshot)
            error = self._validate_decision(decision, plan)
            if error:
                trace.append(TraceEvent(decision=decision))
                return self._result("control_error", error, plan, trace, cost_used)

            if decision.kind == "ask":
                trace.append(TraceEvent(decision=decision))
                return self._result(
                    "needs_input",
                    decision.message or "additional user input is required",
                    plan,
                    trace,
                    cost_used,
                )
            if decision.kind == "escalate":
                trace.append(TraceEvent(decision=decision))
                return self._result(
                    "escalated",
                    decision.message or "the decision was escalated",
                    plan,
                    trace,
                    cost_used,
                )
            if decision.kind == "finish":
                trace.append(TraceEvent(decision=decision))
                return self._result(
                    "completed",
                    decision.message or "objective completed",
                    plan,
                    trace,
                    cost_used,
                )
            if decision.kind == "replan":
                replacement = decision.replacement_plan
                try:
                    self.validate_plan(replacement)
                except PlanValidationError as exc:
                    trace.append(TraceEvent(decision=decision))
                    return self._result(
                        "control_error",
                        f"invalid replacement plan: {exc}",
                        plan,
                        trace,
                        cost_used,
                    )
                plan = replacement
                trace.append(TraceEvent(decision=decision))
                continue

            assert decision.action is not None and decision.step_id is not None
            action = decision.action
            if action.risk == "high":
                trace.append(TraceEvent(decision=decision))
                return self._result(
                    "needs_approval",
                    f"approval required for action {action.name}",
                    plan,
                    trace,
                    cost_used,
                )
            if tool_calls >= self._limits.max_tool_calls:
                trace.append(TraceEvent(decision=decision))
                return self._result(
                    "budget_exhausted",
                    "tool-call budget exhausted",
                    plan,
                    trace,
                    cost_used,
                )
            if cost_used + action.estimated_cost > self._limits.max_cost:
                trace.append(TraceEvent(decision=decision))
                return self._result(
                    "budget_exhausted",
                    "estimated action cost exceeds the remaining budget",
                    plan,
                    trace,
                    cost_used,
                )

            signature = action.signature
            action_counts[signature] = action_counts.get(signature, 0) + 1
            if action_counts[signature] > self._limits.repeated_action_limit:
                trace.append(TraceEvent(decision=decision))
                return self._result(
                    "loop_detected",
                    "equivalent action repeated without sufficient progress",
                    plan,
                    trace,
                    cost_used,
                )

            observation = execute(action)
            if observation.actual_cost < 0:
                trace.append(TraceEvent(decision=decision, observation=observation))
                return self._result(
                    "control_error",
                    "executor returned a negative cost",
                    plan,
                    trace,
                    cost_used,
                )
            tool_calls += 1
            cost_used += observation.actual_cost
            accepted = observation.success and evaluate(
                self._step_by_id(plan, decision.step_id), observation
            )
            trace.append(
                TraceEvent(
                    decision=decision,
                    observation=observation,
                    accepted=accepted,
                )
            )
            if accepted:
                plan = self._set_step_status(plan, decision.step_id, "completed")
            elif not observation.retryable:
                plan = self._set_step_status(plan, decision.step_id, "failed")

            if cost_used > self._limits.max_cost:
                return self._result(
                    "budget_exhausted",
                    "actual execution cost exceeded the budget",
                    plan,
                    trace,
                    cost_used,
                )

        return self._result(
            "budget_exhausted",
            "decision budget exhausted",
            plan,
            trace,
            cost_used,
        )

    @staticmethod
    def validate_plan(plan: Sequence[PlanStep]) -> None:
        if not plan:
            raise PlanValidationError("plan must contain at least one step")
        ids = [step.step_id for step in plan]
        if any(not step_id.strip() for step_id in ids):
            raise PlanValidationError("step IDs must not be empty")
        if len(ids) != len(set(ids)):
            raise PlanValidationError("step IDs must be unique")
        known = set(ids)
        for step in plan:
            missing = set(step.depends_on) - known
            if missing:
                raise PlanValidationError(
                    f"step {step.step_id} has unknown dependencies: {sorted(missing)}"
                )

        graph: Mapping[str, tuple[str, ...]] = {
            step.step_id: step.depends_on for step in plan
        }
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise PlanValidationError("plan contains a dependency cycle")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in graph[step_id]:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in ids:
            visit(step_id)

    def _validate_decision(
        self, decision: Decision, plan: Sequence[PlanStep]
    ) -> str | None:
        if not decision.observable_basis.strip():
            return "decision must include a concise observable basis"
        if len(decision.observable_basis) > 240:
            return "observable basis must be concise; do not emit hidden chain-of-thought"
        if decision.kind == "finish":
            if any(step.status != "completed" for step in plan):
                return "finish is invalid while plan steps remain incomplete"
            return None
        if decision.kind == "replan":
            if not decision.replacement_plan:
                return "replan requires a replacement plan"
            return None
        if decision.kind in {"ask", "escalate"}:
            if not decision.message:
                return f"{decision.kind} requires a message"
            return None
        if decision.kind != "act":
            return f"unsupported decision kind: {decision.kind}"
        if decision.step_id is None or decision.action is None:
            return "act requires step_id and action"
        if decision.action.name not in self._allowed_actions:
            return f"action is not allowed: {decision.action.name}"
        try:
            step = self._step_by_id(plan, decision.step_id)
        except KeyError:
            return f"unknown step: {decision.step_id}"
        if step.status != "pending":
            return f"step {step.step_id} is not pending"
        statuses = {item.step_id: item.status for item in plan}
        if any(statuses[dependency] != "completed" for dependency in step.depends_on):
            return f"dependencies for step {step.step_id} are incomplete"
        return None

    @staticmethod
    def _step_by_id(plan: Sequence[PlanStep], step_id: str) -> PlanStep:
        for step in plan:
            if step.step_id == step_id:
                return step
        raise KeyError(step_id)

    @staticmethod
    def _set_step_status(
        plan: Sequence[PlanStep], step_id: str, status: StepStatus
    ) -> tuple[PlanStep, ...]:
        return tuple(
            replace(step, status=status) if step.step_id == step_id else step
            for step in plan
        )

    @staticmethod
    def _result(
        status: RunStatus,
        message: str,
        plan: Sequence[PlanStep],
        trace: Sequence[TraceEvent],
        cost_used: float,
    ) -> RunResult:
        return RunResult(status, message, tuple(plan), tuple(trace), cost_used)
