from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Callable, Mapping, Sequence


class PlanError(ValueError):
    """The coordinator rejected an invalid collaboration plan."""


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    capabilities: frozenset[str]
    tools: frozenset[str] = frozenset()


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    objective: str
    capability: str
    depends_on: tuple[str, ...] = ()
    requested_tools: frozenset[str] = frozenset()
    expected_outputs: frozenset[str] = frozenset()
    write_keys: frozenset[str] = frozenset()
    max_tokens: int = 1_000


@dataclass(frozen=True)
class Artifact:
    name: str
    content: str
    source_task_id: str


@dataclass(frozen=True)
class WorkerRequest:
    run_id: str
    task_id: str
    objective: str
    allowed_tools: frozenset[str]
    input_artifacts: Mapping[str, Artifact]
    max_tokens: int


@dataclass(frozen=True)
class WorkerResult:
    summary: str
    artifacts: Mapping[str, str] = field(default_factory=dict)
    token_usage: int = 0
    tool_calls: tuple[str, ...] = ()


Worker = Callable[[WorkerRequest], WorkerResult]


@dataclass
class TaskRecord:
    spec: TaskSpec
    agent_name: str
    status: TaskStatus = TaskStatus.PENDING
    error: str | None = None
    result: WorkerResult | None = None


@dataclass(frozen=True)
class RunReport:
    records: Mapping[str, TaskRecord]
    artifacts: Mapping[str, Artifact]
    batches: tuple[tuple[str, ...], ...]
    token_usage: int

    @property
    def succeeded(self) -> bool:
        return all(record.status == TaskStatus.SUCCEEDED for record in self.records.values())


class Coordinator:
    """A small manager-worker runtime with explicit collaboration contracts."""

    def __init__(
        self,
        agents: Sequence[AgentSpec],
        workers: Mapping[str, Worker],
        *,
        max_parallel: int = 4,
        total_token_budget: int = 10_000,
    ) -> None:
        if max_parallel < 1:
            raise ValueError("max_parallel must be positive")
        if total_token_budget < 1:
            raise ValueError("total_token_budget must be positive")
        self._agents = {agent.name: agent for agent in agents}
        if len(self._agents) != len(agents):
            raise ValueError("agent names must be unique")
        missing_workers = set(self._agents) - set(workers)
        if missing_workers:
            raise ValueError(f"missing workers: {sorted(missing_workers)}")
        self._workers = dict(workers)
        self._max_parallel = max_parallel
        self._total_token_budget = total_token_budget

    def run(self, run_id: str, tasks: Sequence[TaskSpec]) -> RunReport:
        task_map = self._validate_plan(tasks)
        records = {
            task_id: TaskRecord(spec=task, agent_name=self._select_agent(task).name)
            for task_id, task in task_map.items()
        }
        artifacts: dict[str, Artifact] = {}
        batches: list[tuple[str, ...]] = []
        token_usage = 0

        while any(record.status == TaskStatus.PENDING for record in records.values()):
            self._skip_blocked_dependants(records)
            eligible = [
                record
                for record in records.values()
                if record.status == TaskStatus.PENDING
                and all(records[dep].status == TaskStatus.SUCCEEDED for dep in record.spec.depends_on)
            ]
            if not eligible:
                if any(record.status == TaskStatus.PENDING for record in records.values()):
                    raise PlanError("plan made no progress")
                break

            remaining = self._total_token_budget - token_usage
            batch = self._choose_batch(eligible, remaining)
            if not batch:
                for record in eligible:
                    record.status = TaskStatus.FAILED
                    record.error = "run token budget exhausted"
                continue

            batches.append(tuple(record.spec.task_id for record in batch))
            requests: dict[str, WorkerRequest] = {}
            for record in batch:
                record.status = TaskStatus.RUNNING
                requests[record.spec.task_id] = self._build_request(
                    run_id, record, records, artifacts
                )

            with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                future_to_record = {
                    pool.submit(self._workers[record.agent_name], requests[record.spec.task_id]): record
                    for record in batch
                }
                completed: list[tuple[TaskRecord, WorkerResult | Exception]] = []
                for future in as_completed(future_to_record):
                    record = future_to_record[future]
                    try:
                        completed.append((record, future.result()))
                    except Exception as exc:  # The runtime turns worker crashes into task state.
                        completed.append((record, exc))

            for record, outcome in sorted(completed, key=lambda item: item[0].spec.task_id):
                if isinstance(outcome, Exception):
                    record.status = TaskStatus.FAILED
                    record.error = f"worker failed: {type(outcome).__name__}: {outcome}"
                    continue
                error = self._validate_result(record.spec, requests[record.spec.task_id], outcome)
                if error:
                    record.status = TaskStatus.FAILED
                    record.error = error
                    continue
                record.result = outcome
                record.status = TaskStatus.SUCCEEDED
                token_usage += outcome.token_usage
                for name, content in outcome.artifacts.items():
                    key = self._artifact_key(record.spec.task_id, name)
                    artifacts[key] = Artifact(
                        name=name,
                        content=content,
                        source_task_id=record.spec.task_id,
                    )

        return RunReport(
            records=MappingProxyType(records),
            artifacts=MappingProxyType(artifacts),
            batches=tuple(batches),
            token_usage=token_usage,
        )

    def _validate_plan(self, tasks: Sequence[TaskSpec]) -> dict[str, TaskSpec]:
        task_map = {task.task_id: task for task in tasks}
        if len(task_map) != len(tasks):
            raise PlanError("task ids must be unique")
        if not task_map:
            raise PlanError("plan must contain at least one task")
        for task in tasks:
            if not task.task_id or not task.objective or task.max_tokens < 1:
                raise PlanError(f"invalid task contract: {task.task_id!r}")
            unknown = set(task.depends_on) - set(task_map)
            if unknown:
                raise PlanError(f"{task.task_id} has unknown dependencies: {sorted(unknown)}")
            self._select_agent(task)

        indegree = {task_id: 0 for task_id in task_map}
        outgoing: dict[str, list[str]] = {task_id: [] for task_id in task_map}
        for task in tasks:
            for dependency in task.depends_on:
                indegree[task.task_id] += 1
                outgoing[dependency].append(task.task_id)
        ready = sorted(task_id for task_id, degree in indegree.items() if degree == 0)
        visited = 0
        while ready:
            task_id = ready.pop(0)
            visited += 1
            for dependant in outgoing[task_id]:
                indegree[dependant] -= 1
                if indegree[dependant] == 0:
                    ready.append(dependant)
                    ready.sort()
        if visited != len(task_map):
            raise PlanError("task dependency graph contains a cycle")
        return task_map

    def _select_agent(self, task: TaskSpec) -> AgentSpec:
        candidates = [
            agent
            for agent in self._agents.values()
            if task.capability in agent.capabilities
            and task.requested_tools.issubset(agent.tools)
        ]
        if not candidates:
            raise PlanError(
                f"no agent can satisfy {task.task_id}: capability={task.capability!r}, "
                f"tools={sorted(task.requested_tools)}"
            )
        return min(candidates, key=lambda agent: (len(agent.tools), agent.name))

    def _choose_batch(self, eligible: Sequence[TaskRecord], remaining: int) -> list[TaskRecord]:
        batch: list[TaskRecord] = []
        claimed_writes: set[str] = set()
        reserved = 0
        for record in sorted(eligible, key=lambda item: item.spec.task_id):
            task = record.spec
            if task.write_keys & claimed_writes:
                continue
            if reserved + task.max_tokens > remaining:
                continue
            batch.append(record)
            claimed_writes.update(task.write_keys)
            reserved += task.max_tokens
            if len(batch) == self._max_parallel:
                break
        return batch

    def _build_request(
        self,
        run_id: str,
        record: TaskRecord,
        records: Mapping[str, TaskRecord],
        artifacts: Mapping[str, Artifact],
    ) -> WorkerRequest:
        allowed_sources = set(record.spec.depends_on)
        visible = {
            key: artifact
            for key, artifact in artifacts.items()
            if artifact.source_task_id in allowed_sources
            and records[artifact.source_task_id].status == TaskStatus.SUCCEEDED
        }
        return WorkerRequest(
            run_id=run_id,
            task_id=record.spec.task_id,
            objective=record.spec.objective,
            allowed_tools=record.spec.requested_tools,
            input_artifacts=MappingProxyType(visible),
            max_tokens=record.spec.max_tokens,
        )

    @staticmethod
    def _validate_result(
        spec: TaskSpec, request: WorkerRequest, result: WorkerResult
    ) -> str | None:
        if result.token_usage < 0 or result.token_usage > request.max_tokens:
            return "worker exceeded its token budget"
        unexpected_tools = set(result.tool_calls) - set(request.allowed_tools)
        if unexpected_tools:
            return f"worker reported unauthorized tools: {sorted(unexpected_tools)}"
        missing_outputs = set(spec.expected_outputs) - set(result.artifacts)
        if missing_outputs:
            return f"worker omitted required outputs: {sorted(missing_outputs)}"
        if any(not name for name in result.artifacts):
            return "artifact names must be non-empty"
        return None

    @staticmethod
    def _skip_blocked_dependants(records: Mapping[str, TaskRecord]) -> None:
        changed = True
        while changed:
            changed = False
            for record in records.values():
                if record.status != TaskStatus.PENDING:
                    continue
                failed = [
                    dep
                    for dep in record.spec.depends_on
                    if records[dep].status in {TaskStatus.FAILED, TaskStatus.SKIPPED}
                ]
                if failed:
                    record.status = TaskStatus.SKIPPED
                    record.error = f"dependency did not succeed: {sorted(failed)}"
                    changed = True

    @staticmethod
    def _artifact_key(task_id: str, name: str) -> str:
        return f"{task_id}:{name}"
