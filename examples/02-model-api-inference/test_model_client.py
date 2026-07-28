import unittest
from random import Random

from model_client import (
    Completed,
    Failed,
    FinishReason,
    IncompleteStreamError,
    InferenceError,
    RetryPolicy,
    TextDelta,
    Usage,
    collect_stream,
    run_with_retry,
)


class CollectStreamTests(unittest.TestCase):
    def test_returns_only_after_completed_event(self) -> None:
        result = collect_stream(
            [
                TextDelta("hello "),
                TextDelta("world"),
                Completed(
                    FinishReason.STOP,
                    Usage(input_tokens=4, output_tokens=2),
                    request_id="req_1",
                    model="demo-v1",
                ),
            ]
        )

        self.assertEqual(result.text, "hello world")
        self.assertEqual(result.finish_reason, FinishReason.STOP)
        self.assertEqual(result.usage.output_tokens, 2)

    def test_partial_text_without_terminal_event_is_not_success(self) -> None:
        with self.assertRaises(IncompleteStreamError):
            collect_stream([TextDelta("partial")])

    def test_error_event_preserves_retry_classification(self) -> None:
        with self.assertRaises(InferenceError) as captured:
            collect_stream([Failed("invalid_request", "bad input", False)])

        self.assertFalse(captured.exception.retryable)


class RetryTests(unittest.TestCase):
    def test_retries_transient_error_within_budget(self) -> None:
        attempts = 0
        delays: list[float] = []

        def operation():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise InferenceError("overloaded", "busy", True)
            return collect_stream(
                [
                    TextDelta("ok"),
                    Completed(
                        FinishReason.STOP,
                        Usage(1, 1),
                        request_id="req_2",
                        model="demo-v1",
                    ),
                ]
            )

        result = run_with_retry(
            operation,
            RetryPolicy(max_attempts=3),
            random=Random(0),
            sleeper=delays.append,
        )

        self.assertEqual(result.text, "ok")
        self.assertEqual(attempts, 3)
        self.assertEqual(len(delays), 2)

    def test_does_not_retry_permanent_error(self) -> None:
        attempts = 0

        def operation():
            nonlocal attempts
            attempts += 1
            raise InferenceError("authentication", "invalid key", False)

        with self.assertRaises(InferenceError):
            run_with_retry(
                operation,
                RetryPolicy(max_attempts=3),
                sleeper=lambda _: None,
            )

        self.assertEqual(attempts, 1)


if __name__ == "__main__":
    unittest.main()
