import asyncio
import unittest

from tool_executor import (
    Effect,
    ToolCall,
    ToolContext,
    ToolExecutionError,
    ToolExecutor,
    ToolSpec,
    require_exact_string,
)


READ_CONTEXT = ToolContext("tenant-1", "user-1", frozenset({"orders:read"}))
WRITE_CONTEXT = ToolContext(
    "tenant-1", "user-1", frozenset({"orders:read", "orders:write"})
)


def spec_for(handler, **overrides):
    values = {
        "name": "lookup_order",
        "description": "Read one order by its identifier.",
        "input_schema": {"type": "object"},
        "validator": require_exact_string("order_id"),
        "handler": handler,
        "required_scopes": frozenset({"orders:read"}),
        "timeout_seconds": 0.05,
    }
    values.update(overrides)
    return ToolSpec(**values)


class ToolExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_read_returns_structured_success(self) -> None:
        async def handler(_context, arguments, _key):
            return {"id": arguments["order_id"]}

        executor = ToolExecutor([spec_for(handler)])
        result = await executor.execute(
            ToolCall("c1", "lookup_order", {"order_id": "A-1"}), READ_CONTEXT
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.output, {"id": "A-1"})

    async def test_invalid_arguments_do_not_reach_handler(self) -> None:
        called = False

        async def handler(_context, _arguments, _key):
            nonlocal called
            called = True

        executor = ToolExecutor([spec_for(handler)])
        result = await executor.execute(
            ToolCall("c1", "lookup_order", {"wrong": "A-1"}), READ_CONTEXT
        )

        self.assertEqual(result.error_code, "invalid_arguments")
        self.assertFalse(called)

    async def test_unauthorized_tool_is_hidden_and_blocked(self) -> None:
        async def handler(_context, _arguments, _key):
            return "never"

        executor = ToolExecutor(
            [
                spec_for(
                    handler,
                    required_scopes=frozenset({"orders:write"}),
                )
            ]
        )

        self.assertEqual(executor.visible_definitions(READ_CONTEXT), [])
        result = await executor.execute(
            ToolCall("c1", "lookup_order", {"order_id": "A-1"}), READ_CONTEXT
        )
        self.assertEqual(result.error_code, "forbidden")

    async def test_sensitive_write_requires_approval(self) -> None:
        async def handler(_context, _arguments, _key):
            return "cancelled"

        executor = ToolExecutor(
            [
                spec_for(
                    handler,
                    name="cancel_order",
                    required_scopes=frozenset({"orders:write"}),
                    effect=Effect.WRITE,
                    requires_approval=True,
                )
            ]
        )
        result = await executor.execute(
            ToolCall(
                "c1",
                "cancel_order",
                {"order_id": "A-1"},
                idempotency_key="cancel-A-1",
            ),
            WRITE_CONTEXT,
        )

        self.assertEqual(result.error_code, "approval_required")

    async def test_write_requires_idempotency_key(self) -> None:
        async def handler(_context, _arguments, _key):
            return "updated"

        executor = ToolExecutor(
            [
                spec_for(
                    handler,
                    effect=Effect.WRITE,
                    required_scopes=frozenset({"orders:write"}),
                )
            ]
        )
        result = await executor.execute(
            ToolCall("c1", "lookup_order", {"order_id": "A-1"}), WRITE_CONTEXT
        )

        self.assertEqual(result.error_code, "idempotency_key_required")

    async def test_same_idempotency_key_replays_without_second_side_effect(self) -> None:
        executions = 0

        async def handler(_context, _arguments, _key):
            nonlocal executions
            executions += 1
            return {"version": executions}

        executor = ToolExecutor(
            [
                spec_for(
                    handler,
                    effect=Effect.WRITE,
                    required_scopes=frozenset({"orders:write"}),
                )
            ]
        )
        first = await executor.execute(
            ToolCall(
                "c1", "lookup_order", {"order_id": "A-1"}, idempotency_key="k1"
            ),
            WRITE_CONTEXT,
        )
        second = await executor.execute(
            ToolCall(
                "c2", "lookup_order", {"order_id": "A-1"}, idempotency_key="k1"
            ),
            WRITE_CONTEXT,
        )

        self.assertTrue(first.ok)
        self.assertTrue(second.replayed)
        self.assertEqual(executions, 1)
        self.assertEqual(second.call_id, "c2")

    async def test_read_timeout_is_retryable(self) -> None:
        async def handler(_context, _arguments, _key):
            await asyncio.sleep(0.1)

        executor = ToolExecutor([spec_for(handler)])
        result = await executor.execute(
            ToolCall("c1", "lookup_order", {"order_id": "A-1"}), READ_CONTEXT
        )

        self.assertEqual(result.error_code, "timeout")
        self.assertTrue(result.retryable)
        self.assertTrue(result.outcome_known)

    async def test_write_timeout_has_unknown_outcome(self) -> None:
        async def handler(_context, _arguments, _key):
            await asyncio.sleep(0.1)

        executor = ToolExecutor(
            [
                spec_for(
                    handler,
                    effect=Effect.WRITE,
                    required_scopes=frozenset({"orders:write"}),
                )
            ]
        )
        result = await executor.execute(
            ToolCall(
                "c1", "lookup_order", {"order_id": "A-1"}, idempotency_key="k1"
            ),
            WRITE_CONTEXT,
        )

        self.assertEqual(result.error_code, "outcome_unknown")
        self.assertFalse(result.retryable)
        self.assertFalse(result.outcome_known)

    async def test_expected_business_error_is_safe_for_model(self) -> None:
        async def handler(_context, _arguments, _key):
            raise ToolExecutionError("not_found", "Order does not exist.")

        executor = ToolExecutor([spec_for(handler)])
        result = await executor.execute(
            ToolCall("c1", "lookup_order", {"order_id": "A-1"}), READ_CONTEXT
        )

        self.assertEqual(result.error_code, "not_found")
        self.assertEqual(result.error_message, "Order does not exist.")

    async def test_invalid_tool_output_is_rejected(self) -> None:
        async def handler(_context, _arguments, _key):
            return {"status": 17}

        def validate_output(output):
            if not isinstance(output, dict) or not isinstance(output.get("status"), str):
                raise ValueError("status must be a string")

        executor = ToolExecutor(
            [spec_for(handler, output_validator=validate_output)]
        )
        result = await executor.execute(
            ToolCall("c1", "lookup_order", {"order_id": "A-1"}), READ_CONTEXT
        )

        self.assertEqual(result.error_code, "invalid_tool_output")
        self.assertIsNone(result.output)


if __name__ == "__main__":
    unittest.main()
