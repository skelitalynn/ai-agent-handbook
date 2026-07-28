"""Minimal Tool Engineering controls without a framework.

This example demonstrates trusted registration, visibility filtering, argument
validation, approval, idempotency, timeout handling, and structured results.
The in-memory idempotency store is educational, not production persistence.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from enum import Enum
from typing import Awaitable, Callable, Mapping


JsonObject = Mapping[str, object]


class Effect(str, Enum):
    READ = "read"
    WRITE = "write"
    IRREVERSIBLE = "irreversible"


@dataclass(frozen=True)
class ToolContext:
    tenant_id: str
    user_id: str
    scopes: frozenset[str]


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: JsonObject
    idempotency_key: str | None = None


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    name: str
    ok: bool
    output: object | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    outcome_known: bool = True
    replayed: bool = False


class ToolExecutionError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.retryable = retryable


Validator = Callable[[JsonObject], None]
OutputValidator = Callable[[object], None]
Handler = Callable[[ToolContext, JsonObject, str | None], Awaitable[object]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: JsonObject
    validator: Validator
    handler: Handler
    output_schema: JsonObject | None = None
    output_validator: OutputValidator | None = None
    required_scopes: frozenset[str] = frozenset()
    effect: Effect = Effect.READ
    requires_approval: bool = False
    timeout_seconds: float = 2.0

    def model_definition(self) -> dict[str, object]:
        definition: dict[str, object] = {
            "name": self.name,
            "description": self.description,
            "input_schema": dict(self.input_schema),
        }
        if self.output_schema is not None:
            definition["output_schema"] = dict(self.output_schema)
        return definition


class ToolExecutor:
    def __init__(self, specs: list[ToolSpec]) -> None:
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs:
            if spec.name in self._specs:
                raise ValueError(f"duplicate tool: {spec.name}")
            if spec.timeout_seconds <= 0:
                raise ValueError("timeout_seconds must be positive")
            self._specs[spec.name] = spec
        self._idempotency: dict[tuple[str, str, str, str], ToolResult] = {}

    def visible_definitions(self, context: ToolContext) -> list[dict[str, object]]:
        """Do not advertise tools the caller cannot invoke."""
        return [
            spec.model_definition()
            for spec in self._specs.values()
            if spec.required_scopes <= context.scopes
        ]

    async def execute(
        self,
        call: ToolCall,
        context: ToolContext,
        *,
        approved: bool = False,
    ) -> ToolResult:
        spec = self._specs.get(call.name)
        if spec is None:
            return self._error(call, "unknown_tool", "Tool is not registered.")

        if not spec.required_scopes <= context.scopes:
            return self._error(call, "forbidden", "Caller is not authorized.")

        try:
            spec.validator(call.arguments)
        except ValueError as exc:
            return self._error(call, "invalid_arguments", str(exc))
        except Exception:
            return self._error(
                call, "validator_error", "Argument validation failed unexpectedly."
            )

        if spec.requires_approval and not approved:
            return self._error(
                call, "approval_required", "Explicit user approval is required."
            )

        cache_key: tuple[str, str, str, str] | None = None
        if spec.effect is not Effect.READ:
            if not call.idempotency_key:
                return self._error(
                    call,
                    "idempotency_key_required",
                    "Write tools require an idempotency key.",
                )
            cache_key = (
                context.tenant_id,
                context.user_id,
                spec.name,
                call.idempotency_key,
            )
            previous = self._idempotency.get(cache_key)
            if previous is not None:
                return replace(previous, call_id=call.call_id, replayed=True)

        try:
            output = await asyncio.wait_for(
                spec.handler(context, call.arguments, call.idempotency_key),
                timeout=spec.timeout_seconds,
            )
        except TimeoutError:
            if spec.effect is Effect.READ:
                return self._error(
                    call,
                    "timeout",
                    "Tool timed out before returning a result.",
                    retryable=True,
                )
            return self._error(
                call,
                "outcome_unknown",
                "Write timed out; the side effect may already have happened.",
                outcome_known=False,
            )
        except ToolExecutionError as exc:
            return self._error(
                call,
                exc.code,
                exc.public_message,
                retryable=exc.retryable,
            )
        except Exception:
            # Internal details belong in protected logs, not model-visible output.
            return self._error(
                call, "internal_error", "Tool execution failed unexpectedly."
            )

        if spec.output_validator is not None:
            try:
                spec.output_validator(output)
            except (TypeError, ValueError):
                return self._error(
                    call,
                    "invalid_tool_output",
                    "Tool returned data that violates its output contract.",
                )

        result = ToolResult(call.call_id, call.name, ok=True, output=output)
        if cache_key is not None:
            self._idempotency[cache_key] = result
        return result

    @staticmethod
    def _error(
        call: ToolCall,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        outcome_known: bool = True,
    ) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            ok=False,
            error_code=code,
            error_message=message,
            retryable=retryable,
            outcome_known=outcome_known,
        )


def require_exact_string(field: str) -> Validator:
    """Small validator for the example; production code should use JSON Schema."""

    def validate(arguments: JsonObject) -> None:
        if set(arguments) != {field}:
            raise ValueError(f"expected exactly one field: {field}")
        if not isinstance(arguments[field], str) or not arguments[field]:
            raise ValueError(f"{field} must be a non-empty string")

    return validate


async def _demo() -> None:
    async def lookup(
        _context: ToolContext, arguments: JsonObject, _key: str | None
    ) -> object:
        return {"order_id": arguments["order_id"], "status": "shipped"}

    executor = ToolExecutor(
        [
            ToolSpec(
                name="lookup_order",
                description="Read the current status of one order owned by the caller.",
                input_schema={
                    "type": "object",
                    "properties": {"order_id": {"type": "string"}},
                    "required": ["order_id"],
                    "additionalProperties": False,
                },
                validator=require_exact_string("order_id"),
                handler=lookup,
                required_scopes=frozenset({"orders:read"}),
            )
        ]
    )
    context = ToolContext("tenant-1", "user-7", frozenset({"orders:read"}))
    result = await executor.execute(
        ToolCall("call-1", "lookup_order", {"order_id": "A-17"}), context
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(_demo())
