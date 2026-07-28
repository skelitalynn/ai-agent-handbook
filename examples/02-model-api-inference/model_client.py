"""A provider-neutral, typed model-stream client used by chapter 02.

This is teaching code: it demonstrates terminal-event handling and bounded retry.
It deliberately does not call a real provider SDK.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from random import Random
from time import sleep
from typing import Callable, Iterable, TypeAlias


class FinishReason(str, Enum):
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALL = "tool_call"
    REFUSAL = "refusal"


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class Completed:
    finish_reason: FinishReason
    usage: Usage
    request_id: str
    model: str


@dataclass(frozen=True)
class Failed:
    code: str
    message: str
    retryable: bool


StreamEvent: TypeAlias = TextDelta | Completed | Failed


@dataclass(frozen=True)
class ModelResult:
    text: str
    finish_reason: FinishReason
    usage: Usage
    request_id: str
    model: str


class InferenceError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.retryable = retryable


class IncompleteStreamError(InferenceError):
    def __init__(self) -> None:
        super().__init__(
            code="incomplete_stream",
            message="stream ended without a terminal event",
            retryable=True,
        )


def collect_stream(events: Iterable[StreamEvent]) -> ModelResult:
    """Accumulate deltas and return only after an explicit completed event."""
    text_parts: list[str] = []
    for event in events:
        if isinstance(event, TextDelta):
            text_parts.append(event.text)
        elif isinstance(event, Completed):
            return ModelResult(
                text="".join(text_parts),
                finish_reason=event.finish_reason,
                usage=event.usage,
                request_id=event.request_id,
                model=event.model,
            )
        elif isinstance(event, Failed):
            raise InferenceError(event.code, event.message, event.retryable)
        else:  # Defensive check for adapters that bypass static typing.
            raise TypeError(f"unsupported event: {event!r}")
    raise IncompleteStreamError()


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays must be non-negative")


def run_with_retry(
    operation: Callable[[], ModelResult],
    policy: RetryPolicy,
    *,
    random: Random | None = None,
    sleeper: Callable[[float], None] = sleep,
) -> ModelResult:
    """Retry only errors classified as transient, with bounded full jitter."""
    random = random or Random()
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return operation()
        except InferenceError as error:
            if not error.retryable or attempt == policy.max_attempts:
                raise
            ceiling = min(
                policy.max_delay_seconds,
                policy.base_delay_seconds * (2 ** (attempt - 1)),
            )
            sleeper(random.uniform(0, ceiling))
    raise AssertionError("the retry loop must return or raise")


def demo() -> None:
    attempts = 0

    def simulated_provider_call() -> ModelResult:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise InferenceError("overloaded", "try again later", retryable=True)
        return collect_stream(
            [
                TextDelta("模型 API "),
                TextDelta("返回类型化事件。"),
                Completed(
                    finish_reason=FinishReason.STOP,
                    usage=Usage(input_tokens=12, output_tokens=9),
                    request_id="req_demo",
                    model="demo-model-v1",
                ),
            ]
        )

    result = run_with_retry(
        simulated_provider_call,
        RetryPolicy(),
        random=Random(0),
        sleeper=lambda _: None,
    )
    print(result)


if __name__ == "__main__":
    demo()
