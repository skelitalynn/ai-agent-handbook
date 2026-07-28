"""A minimal, vendor-neutral Agent Loop.

The model proposes a typed decision. The runtime owns tool execution,
observations, termination, and the observable trace.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Mapping, Protocol, TypeAlias


JsonObject = Mapping[str, object]
Tool = Callable[[JsonObject], object]


@dataclass(frozen=True)
class UserMessage:
    text: str


@dataclass(frozen=True)
class ToolObservation:
    call_id: str
    tool_name: str
    ok: bool
    output: object | None = None
    error: str | None = None


HistoryItem: TypeAlias = UserMessage | ToolObservation


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    tool_name: str
    arguments: JsonObject


@dataclass(frozen=True)
class FinalAnswer:
    text: str


@dataclass(frozen=True)
class NeedUserInput:
    question: str


Decision: TypeAlias = ToolCall | FinalAnswer | NeedUserInput


class DecisionModel(Protocol):
    def decide(self, history: tuple[HistoryItem, ...]) -> Decision:
        """Return the next typed decision for the current run."""


@dataclass(frozen=True)
class TraceEvent:
    step: int
    kind: str
    data: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RunResult:
    status: str
    final_answer: str | None
    pending_question: str | None
    error: str | None
    history: tuple[HistoryItem, ...]
    trace: tuple[TraceEvent, ...]


class AgentRuntime:
    def __init__(
        self,
        model: DecisionModel,
        tools: Mapping[str, Tool],
        *,
        max_steps: int = 8,
        max_identical_calls: int = 2,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        if max_identical_calls < 1:
            raise ValueError("max_identical_calls must be at least 1")
        self._model = model
        self._tools = dict(tools)
        self._max_steps = max_steps
        self._max_identical_calls = max_identical_calls

    def run(self, user_input: str) -> RunResult:
        history: list[HistoryItem] = [UserMessage(user_input)]
        trace: list[TraceEvent] = []
        call_counts: Counter[str] = Counter()

        for step in range(1, self._max_steps + 1):
            decision = self._model.decide(tuple(history))
            trace.append(
                TraceEvent(step, "model_decision", {"type": type(decision).__name__})
            )

            if isinstance(decision, FinalAnswer):
                if not decision.text.strip():
                    return self._failed(
                        "empty final answer", history, trace, step
                    )
                trace.append(TraceEvent(step, "run_completed"))
                return RunResult(
                    status="completed",
                    final_answer=decision.text,
                    pending_question=None,
                    error=None,
                    history=tuple(history),
                    trace=tuple(trace),
                )

            if isinstance(decision, NeedUserInput):
                trace.append(TraceEvent(step, "run_interrupted"))
                return RunResult(
                    status="interrupted",
                    final_answer=None,
                    pending_question=decision.question,
                    error=None,
                    history=tuple(history),
                    trace=tuple(trace),
                )

            signature = self._call_signature(decision)
            call_counts[signature] += 1
            if call_counts[signature] > self._max_identical_calls:
                return self._failed(
                    f"repeated tool call: {decision.tool_name}",
                    history,
                    trace,
                    step,
                )

            observation = self._execute(decision)
            history.append(observation)
            trace.append(
                TraceEvent(
                    step,
                    "tool_observation",
                    {
                        "call_id": observation.call_id,
                        "tool_name": observation.tool_name,
                        "ok": observation.ok,
                    },
                )
            )

        return self._failed(
            f"maximum steps exceeded: {self._max_steps}",
            history,
            trace,
            self._max_steps,
        )

    def _execute(self, call: ToolCall) -> ToolObservation:
        tool = self._tools.get(call.tool_name)
        if tool is None:
            return ToolObservation(
                call.call_id,
                call.tool_name,
                ok=False,
                error="unknown tool",
            )
        try:
            output = tool(call.arguments)
        except Exception as exc:  # Convert tool failures into explicit observations.
            return ToolObservation(
                call.call_id,
                call.tool_name,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
            )
        return ToolObservation(
            call.call_id,
            call.tool_name,
            ok=True,
            output=output,
        )

    @staticmethod
    def _call_signature(call: ToolCall) -> str:
        arguments = json.dumps(
            dict(call.arguments), ensure_ascii=False, sort_keys=True, default=repr
        )
        return f"{call.tool_name}:{arguments}"

    @staticmethod
    def _failed(
        error: str,
        history: list[HistoryItem],
        trace: list[TraceEvent],
        step: int,
    ) -> RunResult:
        trace.append(TraceEvent(step, "run_failed", {"error": error}))
        return RunResult(
            status="failed",
            final_answer=None,
            pending_question=None,
            error=error,
            history=tuple(history),
            trace=tuple(trace),
        )


class ScriptedModel:
    """A deterministic model double for examples and tests."""

    def __init__(self, decisions: list[Decision]) -> None:
        self._decisions = iter(decisions)
        self.seen_histories: list[tuple[HistoryItem, ...]] = []

    def decide(self, history: tuple[HistoryItem, ...]) -> Decision:
        self.seen_histories.append(history)
        return next(self._decisions)


if __name__ == "__main__":
    model = ScriptedModel(
        [
            ToolCall("call-1", "lookup_order", {"order_id": "A-17"}),
            FinalAnswer("订单 A-17 已发货。"),
        ]
    )
    runtime = AgentRuntime(
        model,
        {"lookup_order": lambda args: {"status": "shipped", **dict(args)}},
    )
    print(runtime.run("查询订单 A-17").final_answer)
