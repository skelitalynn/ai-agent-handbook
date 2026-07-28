"""A minimal durable sequential workflow engine built on SQLite.

The example demonstrates orchestration invariants rather than framework syntax:

* workflow progress is reconstructed from an append-only event log;
* every append uses optimistic concurrency;
* approvals are persisted before execution can continue;
* retryable and permanent failures are handled differently;
* completed side effects can be compensated in reverse order;
* an idempotency key is stable across redelivery after a crash.

It intentionally omits scheduling, distributed leases, encryption, retention,
metrics, and production database migration concerns.
"""

from __future__ import annotations

from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Sequence


JSONValue = Any
Activity = Callable[[Mapping[str, JSONValue], str], JSONValue]


class WorkflowError(Exception):
    """Base class for workflow errors."""


class DefinitionError(WorkflowError):
    """The workflow definition violates a structural invariant."""


class RunNotFound(WorkflowError):
    """No event history exists for the requested run."""


class VersionConflict(WorkflowError):
    """Another writer advanced the run after this worker loaded it."""


class VersionMismatch(WorkflowError):
    """The worker definition is incompatible with the persisted run."""


class InvalidTransition(WorkflowError):
    """The requested state transition is not currently allowed."""


class RetryableActivityError(WorkflowError):
    """An activity failed in a way that may succeed on a later attempt."""


class PermanentActivityError(WorkflowError):
    """An activity failed in a way that should not be retried automatically."""


class InjectedCrash(WorkflowError):
    """Test-only crash after a side effect but before workflow acknowledgement."""


class RunStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    COMPENSATING = "compensating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    COMPENSATION_FAILED = "compensation_failed"


TERMINAL_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.COMPENSATION_FAILED,
}


@dataclass(frozen=True)
class Step:
    name: str
    activity: Activity
    compensate: Activity | None = None
    max_attempts: int = 3
    compensation_max_attempts: int = 3
    approval_prompt: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise DefinitionError("step name must not be empty")
        if self.max_attempts < 1:
            raise DefinitionError("max_attempts must be at least 1")
        if self.compensation_max_attempts < 1:
            raise DefinitionError("compensation_max_attempts must be at least 1")


@dataclass(frozen=True)
class WorkflowDefinition:
    version: str
    steps: tuple[Step, ...]

    def __init__(self, version: str, steps: Sequence[Step]) -> None:
        if not version:
            raise DefinitionError("definition version must not be empty")
        step_tuple = tuple(steps)
        names = [step.name for step in step_tuple]
        if len(names) != len(set(names)):
            raise DefinitionError("step names must be unique")
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "steps", step_tuple)


@dataclass(frozen=True)
class Event:
    seq: int
    event_type: str
    payload: dict[str, JSONValue]


@dataclass
class RunState:
    run_id: str
    definition_version: str
    status: RunStatus = RunStatus.RUNNING
    input: dict[str, JSONValue] = field(default_factory=dict)
    outputs: dict[str, JSONValue] = field(default_factory=dict)
    completed_steps: list[str] = field(default_factory=list)
    compensated_steps: list[str] = field(default_factory=list)
    attempts: dict[str, int] = field(default_factory=dict)
    compensation_attempts: dict[str, int] = field(default_factory=dict)
    approval_requested_for: str | None = None
    approvals: dict[str, bool] = field(default_factory=dict)
    compensation_target: RunStatus | None = None
    compensation_reason: str | None = None
    reason: str | None = None
    seq: int = 0

    def context(self) -> dict[str, JSONValue]:
        return {"input": deepcopy(self.input), "outputs": deepcopy(self.outputs)}


class SQLiteEventStore:
    """Append-only event storage with one sequence per workflow run."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_events (
                    run_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (run_id, seq)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def load(self, run_id: str) -> list[Event]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT seq, event_type, payload_json
                FROM workflow_events
                WHERE run_id = ?
                ORDER BY seq
                """,
                (run_id,),
            ).fetchall()
        return [
            Event(
                seq=int(row["seq"]),
                event_type=str(row["event_type"]),
                payload=json.loads(str(row["payload_json"])),
            )
            for row in rows
        ]

    def append(
        self,
        run_id: str,
        expected_seq: int,
        event_type: str,
        payload: Mapping[str, JSONValue],
    ) -> Event:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COALESCE(MAX(seq), 0) AS seq FROM workflow_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            current_seq = int(row["seq"])
            if current_seq != expected_seq:
                connection.rollback()
                raise VersionConflict(
                    f"run {run_id!r} is at seq {current_seq}, expected {expected_seq}"
                )
            event = Event(expected_seq + 1, event_type, dict(payload))
            connection.execute(
                """
                INSERT INTO workflow_events(run_id, seq, event_type, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, event.seq, event.event_type, encoded),
            )
            connection.commit()
            return event


class IdempotentEffectStore:
    """A tiny downstream service that deduplicates by caller operation ID.

    Treat this object as the external system, not as part of the workflow event
    transaction. Calling ``apply`` again with the same logical operation ID
    returns the original result without creating another effect.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS effects (
                    operation_id TEXT PRIMARY KEY,
                    effect_name TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def apply(
        self,
        operation_id: str,
        effect_name: str,
        request: Mapping[str, JSONValue],
    ) -> dict[str, JSONValue]:
        request_json = json.dumps(request, ensure_ascii=False, sort_keys=True)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT effect_name, request_json, result_json
                FROM effects
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            if row is not None:
                if row["effect_name"] != effect_name or row["request_json"] != request_json:
                    connection.rollback()
                    raise InvalidTransition(
                        "an idempotency key cannot be reused for a different intent"
                    )
                return json.loads(str(row["result_json"]))

            result = {
                "effect_id": operation_id,
                "effect": effect_name,
                "request": dict(request),
            }
            result_json = json.dumps(result, ensure_ascii=False, sort_keys=True)
            connection.execute(
                """
                INSERT INTO effects(operation_id, effect_name, request_json, result_json)
                VALUES (?, ?, ?, ?)
                """,
                (operation_id, effect_name, request_json, result_json),
            )
            connection.commit()
            return result

    def count(self) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM effects").fetchone()
        return int(row["count"])


def project(run_id: str, events: Sequence[Event]) -> RunState:
    if not events or events[0].event_type != "RunStarted":
        raise RunNotFound(run_id)

    first = events[0]
    state = RunState(
        run_id=run_id,
        definition_version=str(first.payload["definition_version"]),
        input=deepcopy(first.payload["input"]),
    )

    for event in events:
        state.seq = event.seq
        payload = event.payload
        if event.event_type == "RunStarted":
            continue
        if event.event_type == "StepStarted":
            step_name = str(payload["step"])
            state.attempts[step_name] = state.attempts.get(step_name, 0) + 1
            state.status = RunStatus.RUNNING
        elif event.event_type == "StepCompleted":
            step_name = str(payload["step"])
            if step_name not in state.completed_steps:
                state.completed_steps.append(step_name)
            state.outputs[step_name] = deepcopy(payload["result"])
            state.reason = None
        elif event.event_type == "StepFailed":
            state.reason = str(payload["error"])
        elif event.event_type == "ApprovalRequested":
            state.approval_requested_for = str(payload["step"])
            state.status = RunStatus.PAUSED
        elif event.event_type == "ApprovalDecided":
            step_name = str(payload["step"])
            state.approvals[step_name] = bool(payload["approved"])
            state.approval_requested_for = None
            state.status = RunStatus.RUNNING
        elif event.event_type == "CompensationRequested":
            state.compensation_target = RunStatus(str(payload["target_status"]))
            state.compensation_reason = str(payload["reason"])
            state.reason = state.compensation_reason
            state.status = RunStatus.COMPENSATING
        elif event.event_type == "CompensationStarted":
            step_name = str(payload["step"])
            state.compensation_attempts[step_name] = (
                state.compensation_attempts.get(step_name, 0) + 1
            )
        elif event.event_type == "StepCompensated":
            step_name = str(payload["step"])
            if step_name not in state.compensated_steps:
                state.compensated_steps.append(step_name)
        elif event.event_type == "CompensationAttemptFailed":
            state.reason = str(payload["error"])
        elif event.event_type == "CompensationFailed":
            state.status = RunStatus.COMPENSATION_FAILED
            state.reason = str(payload["error"])
        elif event.event_type == "RunCompleted":
            state.status = RunStatus.COMPLETED
            state.reason = None
        elif event.event_type == "RunFailed":
            state.status = RunStatus.FAILED
            state.reason = str(payload["reason"])
        elif event.event_type == "RunCancelled":
            state.status = RunStatus.CANCELLED
            state.reason = str(payload["reason"])
        else:
            raise WorkflowError(f"unknown event type: {event.event_type}")
    return state


class WorkflowEngine:
    """A deterministic orchestrator for a versioned sequence of activities."""

    def __init__(self, definition: WorkflowDefinition, store: SQLiteEventStore) -> None:
        self.definition = definition
        self.store = store
        self._steps_by_name = {step.name: step for step in definition.steps}

    def get_state(self, run_id: str) -> RunState:
        state = project(run_id, self.store.load(run_id))
        if state.definition_version != self.definition.version:
            raise VersionMismatch(
                f"run uses definition {state.definition_version!r}, "
                f"worker has {self.definition.version!r}"
            )
        return state

    def _append(
        self,
        state: RunState,
        event_type: str,
        payload: Mapping[str, JSONValue],
    ) -> RunState:
        self.store.append(state.run_id, state.seq, event_type, payload)
        return self.get_state(state.run_id)

    def start(
        self,
        run_id: str,
        input_data: Mapping[str, JSONValue],
        *,
        crash_after_effect: str | None = None,
    ) -> RunState:
        if self.store.load(run_id):
            raise InvalidTransition(f"run {run_id!r} already exists")
        self.store.append(
            run_id,
            0,
            "RunStarted",
            {
                "definition_version": self.definition.version,
                "input": dict(input_data),
            },
        )
        return self.advance(run_id, crash_after_effect=crash_after_effect)

    def decide_approval(
        self,
        run_id: str,
        *,
        approved: bool,
        actor: str,
        expected_seq: int | None = None,
    ) -> RunState:
        state = self.get_state(run_id)
        step_name = state.approval_requested_for
        if state.status != RunStatus.PAUSED or step_name is None:
            raise InvalidTransition("the run is not waiting for approval")
        if not actor:
            raise InvalidTransition("approval actor must not be empty")
        self.store.append(
            run_id,
            state.seq if expected_seq is None else expected_seq,
            "ApprovalDecided",
            {"step": step_name, "approved": approved, "actor": actor},
        )
        return self.get_state(run_id)

    def cancel(self, run_id: str, reason: str) -> RunState:
        state = self.get_state(run_id)
        if state.status in TERMINAL_STATUSES:
            return state
        if state.status != RunStatus.COMPENSATING:
            state = self._append(
                state,
                "CompensationRequested",
                {"target_status": RunStatus.CANCELLED.value, "reason": reason},
            )
        return self._continue_compensation(state)

    def advance(
        self,
        run_id: str,
        *,
        crash_after_effect: str | None = None,
    ) -> RunState:
        state = self.get_state(run_id)
        if state.status in TERMINAL_STATUSES:
            return state
        if state.status == RunStatus.PAUSED:
            return state
        if state.status == RunStatus.COMPENSATING:
            return self._continue_compensation(state)

        while state.status == RunStatus.RUNNING:
            if len(state.completed_steps) == len(self.definition.steps):
                return self._append(
                    state,
                    "RunCompleted",
                    {"output": deepcopy(state.outputs)},
                )

            step = self.definition.steps[len(state.completed_steps)]
            if step.approval_prompt is not None and step.name not in state.approvals:
                return self._append(
                    state,
                    "ApprovalRequested",
                    {"step": step.name, "prompt": step.approval_prompt},
                )
            if state.approvals.get(step.name) is False:
                state = self._append(
                    state,
                    "CompensationRequested",
                    {
                        "target_status": RunStatus.CANCELLED.value,
                        "reason": f"approval rejected for step {step.name}",
                    },
                )
                return self._continue_compensation(state)

            if state.attempts.get(step.name, 0) >= step.max_attempts:
                state = self._append(
                    state,
                    "CompensationRequested",
                    {
                        "target_status": RunStatus.FAILED.value,
                        "reason": f"attempt budget exhausted for step {step.name}",
                    },
                )
                return self._continue_compensation(state)

            operation_id = (
                f"{run_id}:{self.definition.version}:{step.name}:execute"
            )
            state = self._append(
                state,
                "StepStarted",
                {"step": step.name, "operation_id": operation_id},
            )
            try:
                result = step.activity(state.context(), operation_id)
                # Ensure persisted results are JSON-compatible before any event append.
                json.dumps(result, ensure_ascii=False, sort_keys=True)
            except RetryableActivityError as error:
                state = self._append(
                    state,
                    "StepFailed",
                    {"step": step.name, "error": str(error), "retryable": True},
                )
                continue
            except Exception as error:
                state = self._append(
                    state,
                    "StepFailed",
                    {"step": step.name, "error": str(error), "retryable": False},
                )
                state = self._append(
                    state,
                    "CompensationRequested",
                    {
                        "target_status": RunStatus.FAILED.value,
                        "reason": f"step {step.name} failed permanently: {error}",
                    },
                )
                return self._continue_compensation(state)

            if crash_after_effect == step.name:
                raise InjectedCrash(
                    f"crashed after {step.name} side effect but before StepCompleted"
                )

            state = self._append(
                state,
                "StepCompleted",
                {"step": step.name, "operation_id": operation_id, "result": result},
            )

        return state

    def _continue_compensation(self, state: RunState) -> RunState:
        if state.status != RunStatus.COMPENSATING:
            return state

        for step_name in reversed(state.completed_steps):
            if step_name in state.compensated_steps:
                continue
            step = self._steps_by_name[step_name]
            if step.compensate is None:
                continue

            while (
                state.compensation_attempts.get(step_name, 0)
                < step.compensation_max_attempts
            ):
                operation_id = (
                    f"{state.run_id}:{self.definition.version}:{step.name}:compensate"
                )
                state = self._append(
                    state,
                    "CompensationStarted",
                    {"step": step.name, "operation_id": operation_id},
                )
                try:
                    result = step.compensate(state.context(), operation_id)
                    json.dumps(result, ensure_ascii=False, sort_keys=True)
                except RetryableActivityError as error:
                    state = self._append(
                        state,
                        "CompensationAttemptFailed",
                        {"step": step.name, "error": str(error), "retryable": True},
                    )
                    continue
                except Exception as error:
                    return self._append(
                        state,
                        "CompensationFailed",
                        {"step": step.name, "error": str(error)},
                    )

                state = self._append(
                    state,
                    "StepCompensated",
                    {"step": step.name, "operation_id": operation_id, "result": result},
                )
                break

            if step_name not in state.compensated_steps:
                return self._append(
                    state,
                    "CompensationFailed",
                    {
                        "step": step_name,
                        "error": f"compensation attempt budget exhausted for {step_name}",
                    },
                )

        target = state.compensation_target
        if target == RunStatus.CANCELLED:
            return self._append(
                state,
                "RunCancelled",
                {"reason": state.compensation_reason or "cancelled"},
            )
        return self._append(
            state,
            "RunFailed",
            {"reason": state.compensation_reason or "workflow failed"},
        )


def build_demo_definition(effect_store: IdempotentEffectStore) -> WorkflowDefinition:
    """Create a small order workflow used by the command-line demo."""

    def reserve(context: Mapping[str, JSONValue], operation_id: str) -> JSONValue:
        return effect_store.apply(
            operation_id,
            "reserve_inventory",
            {"sku": context["input"]["sku"]},
        )

    def release(context: Mapping[str, JSONValue], operation_id: str) -> JSONValue:
        return effect_store.apply(
            operation_id,
            "release_inventory",
            {"reservation": context["outputs"]["reserve"]},
        )

    def charge(context: Mapping[str, JSONValue], operation_id: str) -> JSONValue:
        return effect_store.apply(
            operation_id,
            "charge_payment",
            {"amount": context["input"]["amount"]},
        )

    return WorkflowDefinition(
        version="order-v1",
        steps=(
            Step("reserve", reserve, compensate=release),
            Step("charge", charge, approval_prompt="Approve payment?"),
        ),
    )


if __name__ == "__main__":
    workdir = Path("workflow-demo")
    workdir.mkdir(exist_ok=True)
    effects = IdempotentEffectStore(workdir / "effects.sqlite3")
    engine = WorkflowEngine(
        build_demo_definition(effects),
        SQLiteEventStore(workdir / "events.sqlite3"),
    )
    try:
        state = engine.start("order-001", {"sku": "book", "amount": 99})
    except InvalidTransition:
        state = engine.get_state("order-001")
    if state.status == RunStatus.PAUSED:
        engine.decide_approval("order-001", approved=True, actor="demo-user")
        state = engine.advance("order-001")
    print(json.dumps(state.__dict__, ensure_ascii=False, indent=2, default=str))
