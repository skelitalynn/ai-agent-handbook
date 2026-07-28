"""A minimal, serializable control plane for human-agent interaction.

The implementation focuses on testable invariants:

* the runtime, not the model, assigns action risk;
* approval is bound to an exact action snapshot and expires;
* accept, decline, and cancel remain distinct decisions;
* paused state can be serialized and restored in another process;
* correcting an action invalidates all transitive dependants;
* public progress events omit tool arguments and hidden reasoning.

It is teaching code, not an authentication, authorization, or workflow product.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum, IntEnum
import hashlib
import json
from typing import Any, Mapping, Sequence


JSONValue = Any


class InteractionError(Exception):
    """Base class for interaction control errors."""


class InvalidState(InteractionError):
    """The requested transition is not allowed from the current state."""


class AuthorizationError(InteractionError):
    """The actor is not allowed to make the requested decision."""


class ValidationError(InteractionError):
    """Structured user input does not satisfy the declared contract."""


class RiskLevel(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    PROHIBITED = 4


class ApprovalMode(str, Enum):
    AUTO = "auto"
    REQUIRE = "require"
    BLOCK = "block"


class Decision(str, Enum):
    ACCEPT = "accept"
    DECLINE = "decline"
    CANCEL = "cancel"


class RunStatus(str, Enum):
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class ActionStatus(str, Enum):
    AUTHORIZED = "authorized"
    WAITING_APPROVAL = "waiting_approval"
    BLOCKED = "blocked"
    REJECTED = "rejected"
    DISMISSED = "dismissed"
    EXPIRED = "expired"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    INVALIDATED = "invalidated"
    CANCELLED = "cancelled"


class RequestStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass(frozen=True)
class ToolRule:
    risk: RiskLevel
    approval_mode: ApprovalMode
    reversible: bool
    external_effect: bool

    def __post_init__(self) -> None:
        if self.risk == RiskLevel.PROHIBITED and self.approval_mode != ApprovalMode.BLOCK:
            raise ValidationError("prohibited tools must use block mode")


@dataclass
class ActionRecord:
    action_id: str
    tool_name: str
    arguments: dict[str, JSONValue]
    observable_basis: str
    depends_on: tuple[str, ...]
    risk: RiskLevel
    reversible: bool
    external_effect: bool
    policy_version: str
    run_revision: int
    digest: str
    idempotency_key: str
    status: ActionStatus
    approval_request_id: str | None = None
    artifact_summary: str | None = None
    failure_reason: str | None = None


@dataclass
class ApprovalRequest:
    request_id: str
    action_id: str
    action_digest: str
    summary: str
    risk: RiskLevel
    reversible: bool
    policy_version: str
    requested_at: int
    expires_at: int
    status: RequestStatus = RequestStatus.PENDING
    decided_by: str | None = None
    decided_at: int | None = None


@dataclass
class InputRequest:
    request_id: str
    kind: str
    question: str
    why: str
    required_fields: tuple[str, ...]
    status: RequestStatus = RequestStatus.PENDING
    content: dict[str, JSONValue] | None = None


@dataclass(frozen=True)
class ProgressEvent:
    sequence: int
    kind: str
    message: str
    completed_units: int | None = None
    total_units: int | None = None
    artifact_summary: str | None = None


@dataclass(frozen=True)
class Correction:
    target_action_id: str
    actor: str
    instruction: str
    invalidated_action_ids: tuple[str, ...]
    revision: int


@dataclass
class InteractionState:
    run_id: str
    policy_version: str
    status: RunStatus = RunStatus.RUNNING
    revision: int = 1
    actions: dict[str, ActionRecord] = field(default_factory=dict)
    approvals: dict[str, ApprovalRequest] = field(default_factory=dict)
    input_requests: dict[str, InputRequest] = field(default_factory=dict)
    progress: list[ProgressEvent] = field(default_factory=list)
    corrections: list[Correction] = field(default_factory=list)
    cancelled_reason: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, default=_json_default)

    @classmethod
    def from_json(cls, raw: str) -> "InteractionState":
        data = json.loads(raw)
        state = cls(
            run_id=data["run_id"],
            policy_version=data["policy_version"],
            status=RunStatus(data["status"]),
            revision=int(data["revision"]),
            cancelled_reason=data.get("cancelled_reason"),
        )
        state.actions = {
            action_id: ActionRecord(
                **{
                    **record,
                    "depends_on": tuple(record["depends_on"]),
                    "risk": RiskLevel(record["risk"]),
                    "status": ActionStatus(record["status"]),
                }
            )
            for action_id, record in data["actions"].items()
        }
        state.approvals = {
            request_id: ApprovalRequest(
                **{
                    **request,
                    "risk": RiskLevel(request["risk"]),
                    "status": RequestStatus(request["status"]),
                }
            )
            for request_id, request in data["approvals"].items()
        }
        state.input_requests = {
            request_id: InputRequest(
                **{
                    **request,
                    "required_fields": tuple(request["required_fields"]),
                    "status": RequestStatus(request["status"]),
                }
            )
            for request_id, request in data["input_requests"].items()
        }
        state.progress = [ProgressEvent(**event) for event in data["progress"]]
        state.corrections = [
            Correction(
                **{
                    **correction,
                    "invalidated_action_ids": tuple(
                        correction["invalidated_action_ids"]
                    ),
                }
            )
            for correction in data["corrections"]
        ]
        return state


def _json_default(value: object) -> JSONValue:
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _canonical_digest(
    run_id: str,
    action_id: str,
    tool_name: str,
    arguments: Mapping[str, JSONValue],
    policy_version: str,
    run_revision: int,
) -> str:
    encoded = json.dumps(
        {
            "run_id": run_id,
            "action_id": action_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "policy_version": policy_version,
            "run_revision": run_revision,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class InteractionController:
    def __init__(
        self,
        *,
        policy_version: str,
        tool_rules: Mapping[str, ToolRule],
        authorized_approvers: set[str],
        approval_ttl_seconds: int = 900,
    ) -> None:
        if not policy_version:
            raise ValidationError("policy_version must not be empty")
        if approval_ttl_seconds < 1:
            raise ValidationError("approval_ttl_seconds must be positive")
        self.policy_version = policy_version
        self.tool_rules = dict(tool_rules)
        self.authorized_approvers = set(authorized_approvers)
        self.approval_ttl_seconds = approval_ttl_seconds

    def start(self, run_id: str) -> InteractionState:
        if not run_id:
            raise ValidationError("run_id must not be empty")
        return InteractionState(run_id=run_id, policy_version=self.policy_version)

    def _ensure_live(self, state: InteractionState) -> None:
        if state.policy_version != self.policy_version:
            raise InvalidState("state policy version does not match this controller")
        if state.status in {RunStatus.CANCELLED, RunStatus.COMPLETED}:
            raise InvalidState(f"run is already {state.status.value}")

    def _add_progress(
        self,
        state: InteractionState,
        kind: str,
        message: str,
        *,
        completed_units: int | None = None,
        total_units: int | None = None,
        artifact_summary: str | None = None,
    ) -> None:
        if completed_units is not None and completed_units < 0:
            raise ValidationError("completed_units must not be negative")
        if total_units is not None and total_units < 0:
            raise ValidationError("total_units must not be negative")
        if (
            completed_units is not None
            and total_units is not None
            and completed_units > total_units
        ):
            raise ValidationError("completed_units cannot exceed total_units")
        state.progress.append(
            ProgressEvent(
                sequence=len(state.progress) + 1,
                kind=kind,
                message=message,
                completed_units=completed_units,
                total_units=total_units,
                artifact_summary=artifact_summary,
            )
        )

    def propose_action(
        self,
        state: InteractionState,
        *,
        action_id: str,
        tool_name: str,
        arguments: Mapping[str, JSONValue],
        observable_basis: str,
        depends_on: Sequence[str] = (),
        now: int,
    ) -> ActionRecord:
        self._ensure_live(state)
        if action_id in state.actions:
            raise InvalidState(f"action {action_id!r} already exists")
        if tool_name not in self.tool_rules:
            raise InvalidState(f"tool {tool_name!r} has no runtime policy")
        if len(observable_basis) > 240:
            raise ValidationError("observable_basis must be at most 240 characters")
        dependency_tuple = tuple(depends_on)
        missing = [dependency for dependency in dependency_tuple if dependency not in state.actions]
        if missing:
            raise ValidationError(f"unknown dependencies: {missing}")

        rule = self.tool_rules[tool_name]
        digest = _canonical_digest(
            state.run_id,
            action_id,
            tool_name,
            arguments,
            self.policy_version,
            state.revision,
        )
        idempotency_key = f"{state.run_id}:{action_id}:{digest[:20]}"
        if rule.approval_mode == ApprovalMode.BLOCK:
            status = ActionStatus.BLOCKED
        elif rule.approval_mode == ApprovalMode.REQUIRE:
            status = ActionStatus.WAITING_APPROVAL
        else:
            status = ActionStatus.AUTHORIZED

        action = ActionRecord(
            action_id=action_id,
            tool_name=tool_name,
            arguments=dict(arguments),
            observable_basis=observable_basis,
            depends_on=dependency_tuple,
            risk=rule.risk,
            reversible=rule.reversible,
            external_effect=rule.external_effect,
            policy_version=self.policy_version,
            run_revision=state.revision,
            digest=digest,
            idempotency_key=idempotency_key,
            status=status,
        )
        state.actions[action_id] = action

        if status == ActionStatus.WAITING_APPROVAL:
            request_id = f"approval:{state.run_id}:{action_id}:{digest[:12]}"
            action.approval_request_id = request_id
            state.approvals[request_id] = ApprovalRequest(
                request_id=request_id,
                action_id=action_id,
                action_digest=digest,
                summary=f"{tool_name}: explicit authorization required",
                risk=rule.risk,
                reversible=rule.reversible,
                policy_version=self.policy_version,
                requested_at=now,
                expires_at=now + self.approval_ttl_seconds,
            )
            state.status = RunStatus.WAITING_APPROVAL
            self._add_progress(state, "waiting_approval", f"Waiting for approval: {tool_name}")
        elif status == ActionStatus.BLOCKED:
            self._add_progress(state, "blocked", f"Blocked by policy: {tool_name}")
        else:
            self._add_progress(state, "authorized", f"Authorized by policy: {tool_name}")
        return action

    def decide_approval(
        self,
        state: InteractionState,
        *,
        request_id: str,
        decision: Decision,
        actor: str,
        now: int,
    ) -> ApprovalRequest:
        self._ensure_live(state)
        if actor not in self.authorized_approvers:
            raise AuthorizationError(f"actor {actor!r} cannot approve this run")
        request = state.approvals.get(request_id)
        if request is None:
            raise InvalidState(f"unknown approval request {request_id!r}")
        if request.status != RequestStatus.PENDING:
            raise InvalidState("approval request has already been resolved")
        action = state.actions[request.action_id]

        request.decided_by = actor
        request.decided_at = now
        if now > request.expires_at:
            request.status = RequestStatus.EXPIRED
            action.status = ActionStatus.EXPIRED
        elif decision == Decision.ACCEPT:
            request.status = RequestStatus.ACCEPTED
            action.status = ActionStatus.AUTHORIZED
        elif decision == Decision.DECLINE:
            request.status = RequestStatus.DECLINED
            action.status = ActionStatus.REJECTED
        else:
            request.status = RequestStatus.CANCELLED
            action.status = ActionStatus.DISMISSED

        state.status = RunStatus.RUNNING
        self._add_progress(
            state,
            f"approval_{request.status.value}",
            f"Approval {request.status.value}: {action.tool_name}",
        )
        return request

    def begin_execution(
        self,
        state: InteractionState,
        *,
        action_id: str,
        current_arguments: Mapping[str, JSONValue],
        now: int,
    ) -> str:
        self._ensure_live(state)
        action = state.actions.get(action_id)
        if action is None:
            raise InvalidState(f"unknown action {action_id!r}")
        if action.status != ActionStatus.AUTHORIZED:
            raise InvalidState(f"action is {action.status.value}, not authorized")
        if any(
            state.actions[dependency].status != ActionStatus.COMPLETED
            for dependency in action.depends_on
        ):
            raise InvalidState("all dependencies must complete before execution")

        current_digest = _canonical_digest(
            state.run_id,
            action.action_id,
            action.tool_name,
            current_arguments,
            self.policy_version,
            action.run_revision,
        )
        if current_digest != action.digest:
            action.status = ActionStatus.INVALIDATED
            raise InvalidState("action arguments changed after authorization")
        if action.approval_request_id is not None:
            request = state.approvals[action.approval_request_id]
            if request.status != RequestStatus.ACCEPTED:
                raise InvalidState("the bound approval was not accepted")
            if now > request.expires_at:
                request.status = RequestStatus.EXPIRED
                action.status = ActionStatus.EXPIRED
                raise InvalidState("approval expired before execution")
            if request.action_digest != current_digest:
                action.status = ActionStatus.INVALIDATED
                raise InvalidState("approval does not match this action snapshot")

        action.status = ActionStatus.EXECUTING
        self._add_progress(state, "action_started", f"Started: {action.tool_name}")
        return action.idempotency_key

    def finish_action(
        self,
        state: InteractionState,
        *,
        action_id: str,
        success: bool,
        artifact_summary: str | None = None,
        failure_reason: str | None = None,
    ) -> ActionRecord:
        if state.policy_version != self.policy_version:
            raise InvalidState("state policy version does not match this controller")
        action = state.actions.get(action_id)
        if action is None or action.status != ActionStatus.EXECUTING:
            raise InvalidState("only an executing action can finish")
        action.artifact_summary = artifact_summary
        action.failure_reason = failure_reason
        action.status = ActionStatus.COMPLETED if success else ActionStatus.FAILED
        self._add_progress(
            state,
            "action_completed" if success else "action_failed",
            f"{'Completed' if success else 'Failed'}: {action.tool_name}",
            artifact_summary=artifact_summary,
        )
        return action

    def request_input(
        self,
        state: InteractionState,
        *,
        request_id: str,
        kind: str,
        question: str,
        why: str,
        required_fields: Sequence[str] = (),
    ) -> InputRequest:
        self._ensure_live(state)
        if kind not in {"clarification", "elicitation"}:
            raise ValidationError("kind must be clarification or elicitation")
        if request_id in state.input_requests:
            raise InvalidState(f"input request {request_id!r} already exists")
        request = InputRequest(
            request_id=request_id,
            kind=kind,
            question=question,
            why=why,
            required_fields=tuple(required_fields),
        )
        state.input_requests[request_id] = request
        state.status = RunStatus.WAITING_INPUT
        self._add_progress(state, "waiting_input", f"Waiting for {kind}")
        return request

    def respond_input(
        self,
        state: InteractionState,
        *,
        request_id: str,
        decision: Decision,
        content: Mapping[str, JSONValue] | None = None,
    ) -> InputRequest:
        self._ensure_live(state)
        request = state.input_requests.get(request_id)
        if request is None or request.status != RequestStatus.PENDING:
            raise InvalidState("input request is not pending")
        if decision == Decision.ACCEPT:
            submitted = dict(content or {})
            missing = [field_name for field_name in request.required_fields if field_name not in submitted]
            if missing:
                raise ValidationError(f"missing required fields: {missing}")
            request.status = RequestStatus.ACCEPTED
            request.content = submitted
        elif decision == Decision.DECLINE:
            request.status = RequestStatus.DECLINED
        else:
            request.status = RequestStatus.CANCELLED
        state.status = RunStatus.RUNNING
        self._add_progress(state, f"input_{request.status.value}", f"Input {request.status.value}")
        return request

    def pause(self, state: InteractionState) -> None:
        self._ensure_live(state)
        state.status = RunStatus.PAUSED
        self._add_progress(state, "paused", "Run paused")

    def resume(self, state: InteractionState) -> None:
        if state.status != RunStatus.PAUSED:
            raise InvalidState("only a manually paused run can resume this way")
        state.status = RunStatus.RUNNING
        self._add_progress(state, "resumed", "Run resumed")

    def correct(
        self,
        state: InteractionState,
        *,
        target_action_id: str,
        actor: str,
        instruction: str,
    ) -> Correction:
        self._ensure_live(state)
        if target_action_id not in state.actions:
            raise InvalidState(f"unknown action {target_action_id!r}")
        if state.actions[target_action_id].status == ActionStatus.EXECUTING:
            raise InvalidState("cancel or finish an executing action before correction")

        invalidated = {target_action_id}
        changed = True
        while changed:
            changed = False
            for action in state.actions.values():
                if action.action_id in invalidated:
                    continue
                if any(dependency in invalidated for dependency in action.depends_on):
                    invalidated.add(action.action_id)
                    changed = True

        irreversible_effects = [
            action_id
            for action_id in invalidated
            if state.actions[action_id].status == ActionStatus.COMPLETED
            and state.actions[action_id].external_effect
        ]
        if irreversible_effects:
            raise InvalidState(
                "completed external effects require compensation before replanning: "
                f"{sorted(irreversible_effects)}"
            )

        for action_id in invalidated:
            action = state.actions[action_id]
            action.status = ActionStatus.INVALIDATED
            if action.approval_request_id:
                approval = state.approvals[action.approval_request_id]
                if approval.status == RequestStatus.PENDING:
                    approval.status = RequestStatus.CANCELLED

        state.revision += 1
        correction = Correction(
            target_action_id=target_action_id,
            actor=actor,
            instruction=instruction,
            invalidated_action_ids=tuple(sorted(invalidated)),
            revision=state.revision,
        )
        state.corrections.append(correction)
        state.status = RunStatus.RUNNING
        self._add_progress(state, "corrected", "Plan revision requested")
        return correction

    def cancel(self, state: InteractionState, reason: str) -> None:
        if state.status in {RunStatus.CANCELLED, RunStatus.COMPLETED}:
            return
        for action in state.actions.values():
            if action.status in {
                ActionStatus.AUTHORIZED,
                ActionStatus.WAITING_APPROVAL,
            }:
                action.status = ActionStatus.CANCELLED
        for request in state.approvals.values():
            if request.status == RequestStatus.PENDING:
                request.status = RequestStatus.CANCELLED
        for request in state.input_requests.values():
            if request.status == RequestStatus.PENDING:
                request.status = RequestStatus.CANCELLED
        state.status = RunStatus.CANCELLED
        state.cancelled_reason = reason
        self._add_progress(state, "cancelled", "Run cancelled")

    def public_progress(self, state: InteractionState) -> list[dict[str, JSONValue]]:
        """Return an intentionally small view that cannot expose tool arguments."""
        return [
            {
                "sequence": event.sequence,
                "kind": event.kind,
                "message": event.message,
                "completed_units": event.completed_units,
                "total_units": event.total_units,
                "artifact_summary": event.artifact_summary,
            }
            for event in state.progress
        ]
