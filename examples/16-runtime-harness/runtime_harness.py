from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Callable, Mapping, Protocol


JSONValue = str | int | float | bool | None


class RuntimeViolation(RuntimeError):
    """A runtime-owned invariant was violated."""


class RunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Event:
    sequence: int
    kind: str
    run_id: str
    data: Mapping[str, JSONValue]


Observer = Callable[[Event], None]


@dataclass(frozen=True)
class Mount:
    name: str
    read_only: bool


class Workspace:
    """A virtual task workspace. It is a path policy, not an OS sandbox."""

    def __init__(self, mounts: tuple[Mount, ...], initial: Mapping[str, str] | None = None):
        self._mounts = {mount.name: mount for mount in mounts}
        if len(self._mounts) != len(mounts):
            raise ValueError("mount names must be unique")
        self._files: dict[str, str] = {}
        for path, content in (initial or {}).items():
            normalized, _ = self._resolve(path)
            self._files[normalized] = content

    def read(self, path: str) -> str:
        normalized, _ = self._resolve(path)
        if normalized not in self._files:
            raise FileNotFoundError(normalized)
        return self._files[normalized]

    def write(self, path: str, content: str) -> None:
        normalized, mount = self._resolve(path)
        if mount.read_only:
            raise RuntimeViolation(f"mount {mount.name!r} is read-only")
        self._files[normalized] = content

    def snapshot(self) -> Mapping[str, str]:
        return MappingProxyType(dict(self._files))

    def _resolve(self, path: str) -> tuple[str, Mount]:
        pure = PurePosixPath(path.replace("\\", "/"))
        if pure.is_absolute() or not pure.parts or ".." in pure.parts or "." in pure.parts:
            raise RuntimeViolation(f"path escapes workspace policy: {path!r}")
        mount = self._mounts.get(pure.parts[0])
        if mount is None:
            raise RuntimeViolation(f"path is outside declared mounts: {path!r}")
        return pure.as_posix(), mount


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    run_id: str
    path: str
    content: str
    sha256: str
    source_step: int


class ArtifactStore:
    def __init__(self) -> None:
        self._artifacts: dict[str, Artifact] = {}

    def publish(self, run_id: str, path: str, content: str, source_step: int) -> Artifact:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        identity = hashlib.sha256(f"{path}\0{content}".encode("utf-8")).hexdigest()
        artifact_id = f"{run_id}:{source_step}:{identity[:16]}"
        artifact = Artifact(artifact_id, run_id, path, content, digest, source_step)
        self._artifacts.setdefault(artifact_id, artifact)
        return self._artifacts[artifact_id]

    def get(self, artifact_id: str) -> Artifact:
        return self._artifacts[artifact_id]


@dataclass(frozen=True)
class ModelRequest:
    goal: str
    step: int
    observations: tuple[str, ...]
    available_tools: tuple[str, ...]


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: Mapping[str, JSONValue] = field(default_factory=dict)


@dataclass(frozen=True)
class FinalAnswer:
    text: str


@dataclass(frozen=True)
class Pause:
    reason: str


Decision = ToolCall | FinalAnswer | Pause
Model = Callable[[ModelRequest], Decision]


@dataclass(frozen=True)
class ToolResult:
    observation: str
    publish_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolContext:
    run_id: str
    step: int
    local_context: Mapping[str, object]
    workspace: Workspace

    def require(self, key: str) -> object:
        if key not in self.local_context:
            raise RuntimeViolation(f"missing local dependency: {key}")
        return self.local_context[key]


Tool = Callable[[ToolContext, Mapping[str, JSONValue]], ToolResult]


@dataclass(frozen=True)
class RuntimePolicy:
    allowed_tools: frozenset[str]
    max_steps: int = 8
    max_tool_calls: int = 8
    publish_mount: str = "outputs"


@dataclass
class RunState:
    run_id: str
    goal: str
    status: RunStatus = RunStatus.CREATED
    step: int = 0
    tool_calls: int = 0
    observations: list[str] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    final_answer: str | None = None
    error: str | None = None
    pause_reason: str | None = None
    cancel_requested: bool = False
    next_event_sequence: int = 1

    def to_json(self) -> str:
        payload = {
            "run_id": self.run_id,
            "goal": self.goal,
            "status": self.status.value,
            "step": self.step,
            "tool_calls": self.tool_calls,
            "observations": self.observations,
            "artifact_ids": self.artifact_ids,
            "final_answer": self.final_answer,
            "error": self.error,
            "pause_reason": self.pause_reason,
            "cancel_requested": self.cancel_requested,
            "next_event_sequence": self.next_event_sequence,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, value: str) -> "RunState":
        payload = json.loads(value)
        payload["status"] = RunStatus(payload["status"])
        return cls(**payload)


class EventSink(Protocol):
    def __call__(self, event: Event) -> None: ...


@dataclass(frozen=True)
class Harness:
    model: Model
    tools: Mapping[str, Tool]
    policy: RuntimePolicy
    workspace: Workspace
    artifacts: ArtifactStore
    observers: tuple[EventSink, ...] = ()
    local_context: Mapping[str, object] = field(default_factory=dict)

    def runtime(self) -> "Runtime":
        return Runtime(self)


class Runtime:
    """The execution authority for the loop assembled by a Harness."""

    def __init__(self, harness: Harness):
        self._harness = harness
        self.events: list[Event] = []
        self.observer_errors: list[str] = []

    def new_state(self, run_id: str, goal: str) -> RunState:
        return RunState(run_id=run_id, goal=goal)

    def cancel(self, state: RunState) -> None:
        state.cancel_requested = True

    def run(self, state: RunState) -> RunState:
        if state.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
            raise RuntimeViolation(f"cannot run terminal state {state.status.value}")
        if state.cancel_requested:
            state.status = RunStatus.CANCELLED
            self._emit(state, "run.cancelled", {})
            return state
        if state.status == RunStatus.PAUSED:
            state.pause_reason = None
            self._emit(state, "run.resumed", {})
        else:
            self._emit(state, "run.started", {})
        state.status = RunStatus.RUNNING

        try:
            while state.status == RunStatus.RUNNING:
                if state.cancel_requested:
                    state.status = RunStatus.CANCELLED
                    self._emit(state, "run.cancelled", {})
                    break
                if state.step >= self._harness.policy.max_steps:
                    raise RuntimeViolation("maximum model steps exceeded")

                state.step += 1
                request = ModelRequest(
                    goal=state.goal,
                    step=state.step,
                    observations=tuple(state.observations),
                    available_tools=tuple(sorted(self._harness.policy.allowed_tools)),
                )
                self._emit(state, "model.started", {"step": state.step})
                decision = self._harness.model(request)
                self._emit(
                    state,
                    "model.completed",
                    {"step": state.step, "decision": type(decision).__name__},
                )

                if isinstance(decision, FinalAnswer):
                    state.final_answer = decision.text
                    state.status = RunStatus.COMPLETED
                    self._emit(state, "run.completed", {})
                elif isinstance(decision, Pause):
                    state.pause_reason = decision.reason
                    state.status = RunStatus.PAUSED
                    self._emit(state, "run.paused", {"reason": decision.reason})
                else:
                    self._execute_tool(state, decision)
        except Exception as exc:
            state.status = RunStatus.FAILED
            state.error = f"{type(exc).__name__}: {exc}"
            self._emit(state, "run.failed", {"error_type": type(exc).__name__})
        return state

    def _execute_tool(self, state: RunState, call: ToolCall) -> None:
        self._emit(state, "tool.requested", {"tool": call.name})
        if call.name not in self._harness.policy.allowed_tools:
            raise RuntimeViolation(f"tool is not allowed by runtime policy: {call.name}")
        tool = self._harness.tools.get(call.name)
        if tool is None:
            raise RuntimeViolation(f"allowed tool is not registered: {call.name}")
        if state.tool_calls >= self._harness.policy.max_tool_calls:
            raise RuntimeViolation("maximum tool calls exceeded")
        if state.cancel_requested:
            raise RuntimeViolation("cancelled before tool execution")

        state.tool_calls += 1
        self._emit(state, "tool.started", {"tool": call.name})
        context = ToolContext(
            run_id=state.run_id,
            step=state.step,
            local_context=self._harness.local_context,
            workspace=self._harness.workspace,
        )
        result = tool(context, MappingProxyType(dict(call.arguments)))
        for path in result.publish_paths:
            normalized = PurePosixPath(path.replace("\\", "/"))
            if not normalized.parts or normalized.parts[0] != self._harness.policy.publish_mount:
                raise RuntimeViolation(f"artifact path is outside publish mount: {path!r}")
            content = self._harness.workspace.read(path)
            artifact = self._harness.artifacts.publish(
                state.run_id, normalized.as_posix(), content, state.step
            )
            state.artifact_ids.append(artifact.artifact_id)
            self._emit(
                state,
                "artifact.published",
                {"artifact_id": artifact.artifact_id, "path": artifact.path},
            )
        state.observations.append(result.observation)
        self._emit(state, "tool.completed", {"tool": call.name})

    def _emit(self, state: RunState, kind: str, data: Mapping[str, JSONValue]) -> None:
        event = Event(
            sequence=state.next_event_sequence,
            kind=kind,
            run_id=state.run_id,
            data=MappingProxyType(dict(data)),
        )
        state.next_event_sequence += 1
        self.events.append(event)
        for observer in self._harness.observers:
            try:
                observer(event)
            except Exception as exc:
                self.observer_errors.append(f"{type(exc).__name__}: {exc}")
