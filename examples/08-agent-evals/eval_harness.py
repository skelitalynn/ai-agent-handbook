"""A minimal deterministic evaluation harness for tool-using agents."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class Event:
    kind: str
    name: str
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class ToolExpectation:
    name: str
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class EvalTask:
    task_id: str
    prompt: str
    expected_outcome: Mapping[str, object]
    tags: tuple[str, ...] = ()
    required_calls: tuple[ToolExpectation, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    max_steps: int | None = None
    max_cost: float | None = None


@dataclass(frozen=True)
class Trial:
    final_output: str
    outcome: Mapping[str, object]
    events: tuple[Event, ...]
    cost: float


@dataclass(frozen=True)
class Grade:
    grader: str
    passed: bool
    detail: str


class Grader(Protocol):
    name: str

    def grade(self, task: EvalTask, trial: Trial) -> Grade: ...


class OutcomeGrader:
    name = "outcome"

    def grade(self, task: EvalTask, trial: Trial) -> Grade:
        mismatches = {
            key: (expected, trial.outcome.get(key))
            for key, expected in task.expected_outcome.items()
            if trial.outcome.get(key) != expected
        }
        if mismatches:
            return Grade(self.name, False, f"outcome mismatches: {mismatches}")
        return Grade(self.name, True, "expected environment state reached")


class ToolPolicyGrader:
    name = "tool_policy"

    def grade(self, task: EvalTask, trial: Trial) -> Grade:
        calls = [event for event in trial.events if event.kind == "tool_call"]
        forbidden = sorted(
            {event.name for event in calls if event.name in task.forbidden_tools}
        )
        if forbidden:
            return Grade(self.name, False, f"forbidden tools called: {forbidden}")

        missing: list[str] = []
        for expected in task.required_calls:
            if not any(
                event.name == expected.name
                and all(event.arguments.get(key) == value for key, value in expected.arguments.items())
                for event in calls
            ):
                missing.append(f"{expected.name}{dict(expected.arguments)}")
        if missing:
            return Grade(self.name, False, f"required calls missing: {missing}")
        return Grade(self.name, True, "tool-call policy satisfied")


class BudgetGrader:
    name = "budget"

    def grade(self, task: EvalTask, trial: Trial) -> Grade:
        if task.max_steps is not None and len(trial.events) > task.max_steps:
            return Grade(
                self.name,
                False,
                f"steps {len(trial.events)} exceed {task.max_steps}",
            )
        if task.max_cost is not None and trial.cost > task.max_cost:
            return Grade(
                self.name,
                False,
                f"cost {trial.cost:.4f} exceeds {task.max_cost:.4f}",
            )
        return Grade(self.name, True, "execution stayed within budget")


@dataclass(frozen=True)
class TrialResult:
    task_id: str
    attempt: int
    passed: bool
    grades: tuple[Grade, ...]


@dataclass(frozen=True)
class SuiteReport:
    trials: tuple[TrialResult, ...]
    trial_success_rate: float
    pass_at_k: float
    pass_pow_k: float
    tag_success_rates: Mapping[str, float]


Runner = Callable[[EvalTask, int], Trial]


def run_suite(
    tasks: Sequence[EvalTask],
    runner: Runner,
    graders: Sequence[Grader],
    *,
    trials_per_task: int,
) -> SuiteReport:
    if not tasks:
        raise ValueError("tasks cannot be empty")
    if trials_per_task <= 0:
        raise ValueError("trials_per_task must be positive")

    results: list[TrialResult] = []
    by_task: dict[str, list[bool]] = defaultdict(list)
    tags_by_task = {task.task_id: task.tags for task in tasks}
    if len(tags_by_task) != len(tasks):
        raise ValueError("task_id values must be unique")

    for task in tasks:
        for attempt in range(trials_per_task):
            trial = runner(task, attempt)
            grades = tuple(grader.grade(task, trial) for grader in graders)
            passed = all(grade.passed for grade in grades)
            results.append(TrialResult(task.task_id, attempt, passed, grades))
            by_task[task.task_id].append(passed)

    trial_success_rate = sum(result.passed for result in results) / len(results)
    pass_at_k = sum(any(values) for values in by_task.values()) / len(by_task)
    pass_pow_k = sum(all(values) for values in by_task.values()) / len(by_task)

    tag_values: dict[str, list[bool]] = defaultdict(list)
    for task_id, values in by_task.items():
        for tag in tags_by_task[task_id]:
            tag_values[tag].extend(values)
    tag_rates = {
        tag: sum(values) / len(values) for tag, values in sorted(tag_values.items())
    }

    return SuiteReport(
        trials=tuple(results),
        trial_success_rate=trial_success_rate,
        pass_at_k=pass_at_k,
        pass_pow_k=pass_pow_k,
        tag_success_rates=tag_rates,
    )


if __name__ == "__main__":
    task = EvalTask(
        task_id="cancel-order",
        prompt="Cancel order A-17.",
        expected_outcome={"order_status": "cancelled"},
        tags=("write", "orders"),
        required_calls=(ToolExpectation("cancel_order", {"order_id": "A-17"}),),
        forbidden_tools=("issue_refund",),
        max_steps=3,
        max_cost=0.05,
    )

    def demo_runner(_task: EvalTask, attempt: int) -> Trial:
        success = attempt != 1
        return Trial(
            final_output="Order cancelled." if success else "I could not cancel it.",
            outcome={"order_status": "cancelled" if success else "pending"},
            events=(Event("tool_call", "cancel_order", {"order_id": "A-17"}),),
            cost=0.02,
        )

    report = run_suite(
        [task],
        demo_runner,
        [OutcomeGrader(), ToolPolicyGrader(), BudgetGrader()],
        trials_per_task=3,
    )
    print(report)
