import unittest

from mini_tracer import InMemoryExporter, SpanContext, Tracer, extract_traceparent


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        current = self.value
        self.value += 0.5
        return current


class IdFactory:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self, byte_count: int) -> str:
        self.value += 1
        return f"{self.value:0{byte_count * 2}x}"


class MiniTracerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.exporter = InMemoryExporter()
        self.tracer = Tracer(
            self.exporter,
            clock=FakeClock(),
            id_factory=IdFactory(),
        )

    def test_nested_spans_share_trace_and_record_parent(self) -> None:
        with self.tracer.start_span("run") as root:
            with self.tracer.start_span("tool") as child:
                self.assertEqual(child.context.trace_id, root.context.trace_id)
        child_record, root_record = self.exporter.records
        self.assertEqual(child_record.parent_span_id, root_record.context.span_id)

    def test_new_root_after_exit_gets_a_new_trace(self) -> None:
        with self.tracer.start_span("first"):
            pass
        with self.tracer.start_span("second"):
            pass
        self.assertNotEqual(
            self.exporter.records[0].context.trace_id,
            self.exporter.records[1].context.trace_id,
        )

    def test_exception_marks_span_and_is_re_raised(self) -> None:
        with self.assertRaises(RuntimeError):
            with self.tracer.start_span("broken"):
                raise RuntimeError("secret detail")
        record = self.exporter.records[0]
        self.assertEqual(record.status, "error")
        self.assertEqual(record.events[0].attributes["exception.type"], "RuntimeError")

    def test_sensitive_content_is_redacted_but_usage_is_kept(self) -> None:
        with self.tracer.start_span(
            "model", attributes={"prompt": "private", "input_tokens": 12}
        ):
            pass
        record = self.exporter.records[0]
        self.assertEqual(record.attributes["prompt"], "[REDACTED]")
        self.assertEqual(record.attributes["input_tokens"], 12)

    def test_event_attributes_are_redacted(self) -> None:
        with self.tracer.start_span("tool") as span:
            span.add_event("result", {"tool_result": "private", "rows": 3})
        event = self.exporter.records[0].events[0]
        self.assertEqual(event.attributes["tool_result"], "[REDACTED]")
        self.assertEqual(event.attributes["rows"], 3)

    def test_duration_is_non_negative(self) -> None:
        with self.tracer.start_span("work"):
            pass
        self.assertEqual(self.exporter.records[0].duration, 0.5)

    def test_traceparent_round_trip(self) -> None:
        with self.tracer.start_span("run") as span:
            parsed = extract_traceparent(span.inject_traceparent())
            self.assertEqual(parsed, span.context)

    def test_remote_parent_continues_trace(self) -> None:
        parent = SpanContext("1" * 32, "2" * 16, sampled=False)
        with self.tracer.start_span("worker", remote_parent=parent) as child:
            self.assertEqual(child.context.trace_id, parent.trace_id)
            self.assertFalse(child.context.sampled)
        self.assertEqual(self.exporter.records[0].parent_span_id, parent.span_id)

    def test_invalid_or_zero_traceparent_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            extract_traceparent("not-a-traceparent")
        with self.assertRaises(ValueError):
            extract_traceparent(f"00-{'0' * 32}-{'1' * 16}-01")


if __name__ == "__main__":
    unittest.main()
