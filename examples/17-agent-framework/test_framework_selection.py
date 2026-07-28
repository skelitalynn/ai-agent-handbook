import unittest

from framework_selection import (
    BenchmarkGate,
    BenchmarkResult,
    CapabilityRequirement,
    EventAdapter,
    FrameworkProfile,
    SelectionError,
    SelectionPolicy,
    StateOwnership,
    Support,
    assess,
    pareto_frontier,
    passes_benchmark,
)


def profile(**overrides):
    values = {
        "name": "candidate",
        "version_pin": "1.2.3",
        "release_channel": "stable",
        "capabilities": {"checkpoint": Support.STABLE, "hitl": Support.STABLE},
        "state_ownership": StateOwnership.APPLICATION,
        "portable_checkpoint": True,
        "event_schema_version": "v1",
    }
    values.update(overrides)
    return FrameworkProfile(**values)


def gate():
    return BenchmarkGate(20, 0.8, 2_000, 0.05, 0.9)


def result(name, success, latency, cost, trace, suite="suite-v1"):
    return BenchmarkResult(name, "1.0.0", suite, 30, success, latency, cost, trace)


class FrameworkSelectionTests(unittest.TestCase):
    def test_stable_required_capabilities_pass_the_hard_gate(self):
        policy = SelectionPolicy((CapabilityRequirement("checkpoint"),))
        decision = assess(profile(), policy)
        self.assertTrue(decision.eligible)
        self.assertEqual(decision.gaps, ())

    def test_missing_capability_disqualifies_candidate(self):
        policy = SelectionPolicy((CapabilityRequirement("sandbox"),))
        decision = assess(profile(), policy)
        self.assertFalse(decision.eligible)
        self.assertIn("missing capability: sandbox", decision.gaps)

    def test_experimental_capability_requires_explicit_acceptance(self):
        candidate = profile(capabilities={"sandbox": Support.EXPERIMENTAL})
        denied = assess(candidate, SelectionPolicy((CapabilityRequirement("sandbox"),)))
        allowed = assess(
            candidate,
            SelectionPolicy((CapabilityRequirement("sandbox", allow_experimental=True),)),
        )
        self.assertFalse(denied.eligible)
        self.assertTrue(allowed.eligible)
        self.assertIn("experimental capability: sandbox", allowed.risks)

    def test_release_channel_is_a_hard_gate(self):
        decision = assess(
            profile(release_channel="preview"),
            SelectionPolicy((CapabilityRequirement("checkpoint"),)),
        )
        self.assertFalse(decision.eligible)

    def test_application_owned_state_can_be_required(self):
        decision = assess(
            profile(state_ownership=StateOwnership.MANAGED_SERVICE),
            SelectionPolicy((), require_application_owned_state=True),
        )
        self.assertFalse(decision.eligible)
        self.assertIn("state is owned by managed_service", decision.gaps)

    def test_nonportable_checkpoint_is_reported_as_risk_or_gap(self):
        candidate = profile(portable_checkpoint=False)
        risk = assess(candidate, SelectionPolicy(()))
        gap = assess(candidate, SelectionPolicy((), require_portable_checkpoint=True))
        self.assertTrue(risk.eligible)
        self.assertTrue(risk.risks)
        self.assertFalse(gap.eligible)

    def test_latest_is_not_an_evaluation_version(self):
        with self.assertRaisesRegex(SelectionError, "exact version pin"):
            profile(version_pin="latest")

    def test_benchmark_gate_rejects_insufficient_trace_coverage(self):
        candidate = result("x", 0.9, 1_000, 0.03, 0.5)
        self.assertFalse(passes_benchmark(candidate, gate()))

    def test_pareto_frontier_removes_a_strictly_dominated_candidate(self):
        better = result("better", 0.9, 900, 0.02, 0.98)
        worse = result("worse", 0.85, 1_200, 0.04, 0.92)
        self.assertEqual(pareto_frontier((better, worse), gate()), (better,))

    def test_pareto_frontier_preserves_real_tradeoffs(self):
        accurate = result("accurate", 0.95, 1_500, 0.04, 0.98)
        cheap = result("cheap", 0.85, 700, 0.01, 0.95)
        self.assertEqual(set(pareto_frontier((accurate, cheap), gate())), {accurate, cheap})

    def test_pareto_comparison_rejects_different_suites(self):
        a = result("a", 0.9, 1_000, 0.02, 0.95, "suite-a")
        b = result("b", 0.9, 1_000, 0.02, 0.95, "suite-b")
        with self.assertRaisesRegex(SelectionError, "same benchmark suite"):
            pareto_frontier((a, b), gate())

    def test_versioned_event_adapter_normalizes_known_events(self):
        adapter = EventAdapter("candidate", "1.2.3", "vendor-v2", {"tool.done": "tool.completed"})
        event = adapter.normalize(
            {
                "schema_version": "vendor-v2",
                "event_id": "evt-1",
                "run_id": "run-1",
                "kind": "tool.done",
                "payload": {"tool": "search"},
            }
        )
        self.assertEqual(event.kind, "tool.completed")
        self.assertEqual(event.source_version, "1.2.3")

    def test_event_adapter_rejects_schema_drift_and_unknown_kinds(self):
        adapter = EventAdapter("candidate", "1.2.3", "vendor-v2", {"tool.done": "tool.completed"})
        with self.assertRaisesRegex(SelectionError, "schema version"):
            adapter.normalize(
                {"schema_version": "vendor-v3", "event_id": "e", "run_id": "r", "kind": "tool.done"}
            )
        with self.assertRaisesRegex(SelectionError, "unmapped"):
            adapter.normalize(
                {"schema_version": "vendor-v2", "event_id": "e", "run_id": "r", "kind": "new.event"}
            )


if __name__ == "__main__":
    unittest.main()
