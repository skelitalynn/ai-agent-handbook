from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Sequence


class SelectionError(ValueError):
    """The comparison itself is invalid or under-specified."""


class Support(str, Enum):
    STABLE = "stable"
    EXPERIMENTAL = "experimental"
    MISSING = "missing"


class StateOwnership(str, Enum):
    APPLICATION = "application"
    FRAMEWORK = "framework"
    MANAGED_SERVICE = "managed_service"


@dataclass(frozen=True)
class FrameworkProfile:
    name: str
    version_pin: str
    release_channel: str
    capabilities: Mapping[str, Support]
    state_ownership: StateOwnership
    portable_checkpoint: bool
    event_schema_version: str

    def __post_init__(self) -> None:
        if not self.name:
            raise SelectionError("framework name is required")
        if not self.version_pin or self.version_pin.lower() in {"latest", "*"}:
            raise SelectionError("framework evaluation requires an exact version pin")
        object.__setattr__(
            self, "capabilities", MappingProxyType(dict(self.capabilities))
        )


@dataclass(frozen=True)
class CapabilityRequirement:
    name: str
    allow_experimental: bool = False


@dataclass(frozen=True)
class SelectionPolicy:
    requirements: tuple[CapabilityRequirement, ...]
    allowed_release_channels: frozenset[str] = frozenset({"stable"})
    require_application_owned_state: bool = False
    require_portable_checkpoint: bool = False


@dataclass(frozen=True)
class Assessment:
    profile: FrameworkProfile
    eligible: bool
    gaps: tuple[str, ...]
    risks: tuple[str, ...]


def assess(profile: FrameworkProfile, policy: SelectionPolicy) -> Assessment:
    gaps: list[str] = []
    risks: list[str] = []
    if profile.release_channel not in policy.allowed_release_channels:
        gaps.append(f"release channel is not allowed: {profile.release_channel}")

    for requirement in policy.requirements:
        level = profile.capabilities.get(requirement.name, Support.MISSING)
        if level == Support.MISSING:
            gaps.append(f"missing capability: {requirement.name}")
        elif level == Support.EXPERIMENTAL:
            if requirement.allow_experimental:
                risks.append(f"experimental capability: {requirement.name}")
            else:
                gaps.append(f"capability is only experimental: {requirement.name}")

    if (
        policy.require_application_owned_state
        and profile.state_ownership != StateOwnership.APPLICATION
    ):
        gaps.append(f"state is owned by {profile.state_ownership.value}")
    elif profile.state_ownership != StateOwnership.APPLICATION:
        risks.append(f"state portability depends on {profile.state_ownership.value}")

    if policy.require_portable_checkpoint and not profile.portable_checkpoint:
        gaps.append("checkpoint format is not portable")
    elif not profile.portable_checkpoint:
        risks.append("checkpoint migration requires a framework-specific adapter")

    return Assessment(profile, not gaps, tuple(gaps), tuple(risks))


@dataclass(frozen=True)
class BenchmarkResult:
    profile_name: str
    version_pin: str
    suite_id: str
    cases: int
    success_rate: float
    p95_latency_ms: float
    mean_cost: float
    trace_completeness: float

    def __post_init__(self) -> None:
        if self.cases < 1:
            raise SelectionError("benchmark must contain cases")
        for name in ("success_rate", "trace_completeness"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise SelectionError(f"{name} must be between 0 and 1")
        if self.p95_latency_ms < 0 or self.mean_cost < 0:
            raise SelectionError("latency and cost must be non-negative")


@dataclass(frozen=True)
class BenchmarkGate:
    min_cases: int
    min_success_rate: float
    max_p95_latency_ms: float
    max_mean_cost: float
    min_trace_completeness: float


def passes_benchmark(result: BenchmarkResult, gate: BenchmarkGate) -> bool:
    return (
        result.cases >= gate.min_cases
        and result.success_rate >= gate.min_success_rate
        and result.p95_latency_ms <= gate.max_p95_latency_ms
        and result.mean_cost <= gate.max_mean_cost
        and result.trace_completeness >= gate.min_trace_completeness
    )


def pareto_frontier(
    results: Sequence[BenchmarkResult], gate: BenchmarkGate
) -> tuple[BenchmarkResult, ...]:
    qualified = [result for result in results if passes_benchmark(result, gate)]
    suites = {result.suite_id for result in qualified}
    if len(suites) > 1:
        raise SelectionError("Pareto comparison requires the same benchmark suite")
    versions = {(result.profile_name, result.version_pin) for result in qualified}
    if len(versions) != len(qualified):
        raise SelectionError("duplicate profile/version benchmark result")

    frontier = [
        candidate
        for candidate in qualified
        if not any(
            _dominates(other, candidate)
            for other in qualified
            if other is not candidate
        )
    ]
    return tuple(sorted(frontier, key=lambda result: (result.profile_name, result.version_pin)))


def _dominates(left: BenchmarkResult, right: BenchmarkResult) -> bool:
    no_worse = (
        left.success_rate >= right.success_rate
        and left.p95_latency_ms <= right.p95_latency_ms
        and left.mean_cost <= right.mean_cost
        and left.trace_completeness >= right.trace_completeness
    )
    strictly_better = (
        left.success_rate > right.success_rate
        or left.p95_latency_ms < right.p95_latency_ms
        or left.mean_cost < right.mean_cost
        or left.trace_completeness > right.trace_completeness
    )
    return no_worse and strictly_better


@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    run_id: str
    kind: str
    source_framework: str
    source_version: str
    payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class EventAdapter:
    framework: str
    framework_version: str
    source_schema_version: str
    kind_map: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind_map", MappingProxyType(dict(self.kind_map)))

    def normalize(self, raw: Mapping[str, object]) -> NormalizedEvent:
        if raw.get("schema_version") != self.source_schema_version:
            raise SelectionError("unsupported framework event schema version")
        event_id = raw.get("event_id")
        run_id = raw.get("run_id")
        source_kind = raw.get("kind")
        if not all(isinstance(value, str) and value for value in (event_id, run_id, source_kind)):
            raise SelectionError("event_id, run_id and kind are required strings")
        if source_kind not in self.kind_map:
            raise SelectionError(f"unmapped framework event kind: {source_kind}")
        payload = raw.get("payload", {})
        if not isinstance(payload, Mapping):
            raise SelectionError("event payload must be a mapping")
        return NormalizedEvent(
            event_id=event_id,
            run_id=run_id,
            kind=self.kind_map[source_kind],
            source_framework=self.framework,
            source_version=self.framework_version,
            payload=MappingProxyType(dict(payload)),
        )
