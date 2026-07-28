"""A dependency-free tracer that demonstrates Agent span semantics."""

from __future__ import annotations

import re
import secrets
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Callable, Iterator, Mapping


TRACEPARENT = re.compile(
    r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$"
)
SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "input",
    "output",
    "prompt",
    "secret",
    "tool_arguments",
    "tool_result",
}


@dataclass(frozen=True)
class SpanContext:
    trace_id: str
    span_id: str
    sampled: bool = True


@dataclass(frozen=True)
class SpanEvent:
    name: str
    timestamp: float
    attributes: Mapping[str, object]


@dataclass(frozen=True)
class SpanRecord:
    name: str
    context: SpanContext
    parent_span_id: str | None
    started_at: float
    ended_at: float
    status: str
    attributes: Mapping[str, object]
    events: tuple[SpanEvent, ...]

    @property
    def duration(self) -> float:
        return self.ended_at - self.started_at


class InMemoryExporter:
    def __init__(self) -> None:
        self.records: list[SpanRecord] = []

    def export(self, record: SpanRecord) -> None:
        self.records.append(record)


@dataclass
class _ActiveSpan:
    name: str
    context: SpanContext
    parent_span_id: str | None
    started_at: float
    attributes: dict[str, object]
    events: list[SpanEvent] = field(default_factory=list)
    status: str = "ok"


class Span:
    def __init__(
        self,
        active: _ActiveSpan,
        *,
        clock: Callable[[], float],
        capture_content: bool,
    ) -> None:
        self._active = active
        self._clock = clock
        self._capture_content = capture_content

    @property
    def context(self) -> SpanContext:
        return self._active.context

    def set_attribute(self, key: str, value: object) -> None:
        self._active.attributes[key] = _redact(key, value, self._capture_content)

    def add_event(self, name: str, attributes: Mapping[str, object] | None = None) -> None:
        safe = {
            key: _redact(key, value, self._capture_content)
            for key, value in (attributes or {}).items()
        }
        self._active.events.append(SpanEvent(name, self._clock(), safe))

    def inject_traceparent(self) -> str:
        sampled = "01" if self.context.sampled else "00"
        return f"00-{self.context.trace_id}-{self.context.span_id}-{sampled}"


class Tracer:
    def __init__(
        self,
        exporter: InMemoryExporter,
        *,
        clock: Callable[[], float] = time.time,
        id_factory: Callable[[int], str] = secrets.token_hex,
        capture_content: bool = False,
    ) -> None:
        self._exporter = exporter
        self._clock = clock
        self._id_factory = id_factory
        self._capture_content = capture_content
        self._current: ContextVar[_ActiveSpan | None] = ContextVar(
            f"mini_tracer_current_{id(self)}", default=None
        )

    @contextmanager
    def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, object] | None = None,
        remote_parent: SpanContext | None = None,
    ) -> Iterator[Span]:
        local_parent = self._current.get()
        parent_context = local_parent.context if local_parent else remote_parent
        context = SpanContext(
            trace_id=(
                parent_context.trace_id if parent_context else self._id_factory(16)
            ),
            span_id=self._id_factory(8),
            sampled=parent_context.sampled if parent_context else True,
        )
        safe_attributes = {
            key: _redact(key, value, self._capture_content)
            for key, value in (attributes or {}).items()
        }
        active = _ActiveSpan(
            name=name,
            context=context,
            parent_span_id=parent_context.span_id if parent_context else None,
            started_at=self._clock(),
            attributes=safe_attributes,
        )
        token = self._current.set(active)
        span = Span(
            active,
            clock=self._clock,
            capture_content=self._capture_content,
        )
        try:
            yield span
        except BaseException as exc:
            active.status = "error"
            span.add_event("exception", {"exception.type": type(exc).__name__})
            raise
        finally:
            ended_at = self._clock()
            self._exporter.export(
                SpanRecord(
                    name=active.name,
                    context=active.context,
                    parent_span_id=active.parent_span_id,
                    started_at=active.started_at,
                    ended_at=ended_at,
                    status=active.status,
                    attributes=dict(active.attributes),
                    events=tuple(active.events),
                )
            )
            self._current.reset(token)


def extract_traceparent(value: str) -> SpanContext:
    match = TRACEPARENT.fullmatch(value.strip().lower())
    if match is None:
        raise ValueError("invalid traceparent")
    trace_id, parent_id, flags = match.groups()
    if int(trace_id, 16) == 0 or int(parent_id, 16) == 0:
        raise ValueError("trace and parent IDs cannot be all zero")
    return SpanContext(trace_id, parent_id, sampled=bool(int(flags, 16) & 1))


def _redact(key: str, value: object, capture_content: bool) -> object:
    if not capture_content and key.lower() in SENSITIVE_KEYS:
        return "[REDACTED]"
    return value


if __name__ == "__main__":
    exporter = InMemoryExporter()
    tracer = Tracer(exporter)
    with tracer.start_span("agent.run", attributes={"run_id": "run-42"}):
        with tracer.start_span(
            "model.generate",
            attributes={"model": "example-model", "prompt": "private input"},
        ) as generation:
            generation.set_attribute("input_tokens", 120)
            generation.set_attribute("output_tokens", 30)
        with tracer.start_span("tool.execute", attributes={"tool": "lookup_order"}):
            pass

    for record in exporter.records:
        print(record)
