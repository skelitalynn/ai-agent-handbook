"""A governed, versioned memory store for Chapter 11.

This standard-library example separates memory extraction from memory commit.  A
candidate must pass policy checks before it becomes durable, every overwrite keeps
provenance and revision history, retrieval is namespace-scoped before ranking, and
forgetting redacts every version of a logical key.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import math
import re
from typing import Literal, Sequence


MemoryKind = Literal["semantic", "episodic", "procedural"]
MemoryStatus = Literal["active", "superseded", "deleted"]
TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def tokenize(text: str) -> set[str]:
    return set(TOKEN_PATTERN.findall(text.casefold()))


@dataclass(frozen=True)
class MemoryCandidate:
    kind: MemoryKind
    key: str
    value: str
    source_ref: str
    confidence: float
    importance: float = 0.5
    sensitive: bool = False
    user_confirmed: bool = False
    approved_by: str | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    owner_id: str
    namespace: str
    kind: MemoryKind
    key: str
    value: str
    source_ref: str
    confidence: float
    importance: float
    revision: int
    created_at: datetime
    expires_at: datetime | None
    status: MemoryStatus = "active"
    replaced_by: str | None = None


@dataclass(frozen=True)
class MemoryHit:
    record: MemoryRecord
    score: float

    @property
    def citation(self) -> str:
        return self.record.memory_id


class MemoryPolicyError(ValueError):
    pass


class VersionConflict(ValueError):
    pass


class MemoryStore:
    """An in-memory teaching store; use durable encrypted storage in production."""

    def __init__(self, *, minimum_confidence: float = 0.7):
        if not 0 <= minimum_confidence <= 1:
            raise ValueError("minimum_confidence must be between 0 and 1")
        self._minimum_confidence = minimum_confidence
        self._records: dict[str, MemoryRecord] = {}
        self._active_keys: dict[tuple[str, str, MemoryKind, str], str] = {}
        self._latest_revisions: dict[tuple[str, str, MemoryKind, str], int] = {}
        self._operations: dict[str, tuple[str, str]] = {}

    def commit(
        self,
        *,
        owner_id: str,
        namespace: str,
        candidate: MemoryCandidate,
        operation_id: str,
        expected_revision: int | None = None,
        now: datetime | None = None,
    ) -> MemoryRecord:
        """Validate and atomically upsert one logical memory key."""

        timestamp = now or utc_now()
        self._validate_candidate(candidate, timestamp)
        logical_key = (owner_id, namespace, candidate.kind, candidate.key)
        current_id = self._active_keys.get(logical_key)
        current = self._records[current_id] if current_id else None

        fingerprint = self._operation_fingerprint(
            owner_id, namespace, candidate, expected_revision
        )
        previous_operation = self._operations.get(operation_id)
        if previous_operation is not None:
            previous_fingerprint, memory_id = previous_operation
            if previous_fingerprint != fingerprint:
                raise MemoryPolicyError("operation_id was reused for different content")
            return self._records[memory_id]

        # Revision survives deletion even though the active pointer does not.  This
        # prevents a later re-creation from reusing a historical memory ID.
        current_revision = self._latest_revisions.get(logical_key, 0)
        if expected_revision is not None and expected_revision != current_revision:
            raise VersionConflict(
                f"expected revision {expected_revision}, found {current_revision}"
            )

        revision = current_revision + 1
        memory_id = self._memory_id(logical_key, revision)
        record = MemoryRecord(
            memory_id=memory_id,
            owner_id=owner_id,
            namespace=namespace,
            kind=candidate.kind,
            key=candidate.key,
            value=candidate.value,
            source_ref=candidate.source_ref,
            confidence=candidate.confidence,
            importance=candidate.importance,
            revision=revision,
            created_at=timestamp,
            expires_at=candidate.expires_at,
        )

        # Build the replacement first, then change the visible active pointer.
        if current is not None:
            self._records[current.memory_id] = replace(
                current,
                status="superseded",
                replaced_by=memory_id,
            )
        self._records[memory_id] = record
        self._active_keys[logical_key] = memory_id
        self._latest_revisions[logical_key] = revision
        self._operations[operation_id] = (fingerprint, memory_id)
        return record

    def get_active(
        self,
        *,
        owner_id: str,
        namespace: str,
        kind: MemoryKind,
        key: str,
        now: datetime | None = None,
    ) -> MemoryRecord | None:
        """Read a known profile/fact key without semantic search."""

        logical_key = (owner_id, namespace, kind, key)
        memory_id = self._active_keys.get(logical_key)
        if memory_id is None:
            return None
        record = self._records[memory_id]
        if self._is_expired(record, now or utc_now()):
            return None
        return record

    def search(
        self,
        query: str,
        *,
        owner_id: str,
        namespace: str,
        kinds: Sequence[MemoryKind] | None = None,
        top_k: int = 5,
        now: datetime | None = None,
        recency_half_life_days: float = 30.0,
    ) -> list[MemoryHit]:
        """Retrieve active memories after owner/namespace/expiry filtering."""

        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if recency_half_life_days <= 0:
            raise ValueError("recency_half_life_days must be positive")

        timestamp = now or utc_now()
        allowed_kinds = set(kinds) if kinds else None
        candidates = [
            record
            for record in self._records.values()
            if record.status == "active"
            and record.owner_id == owner_id
            and record.namespace == namespace
            and (allowed_kinds is None or record.kind in allowed_kinds)
            and not self._is_expired(record, timestamp)
        ]

        query_tokens = tokenize(query)
        hits: list[MemoryHit] = []
        for record in candidates:
            record_tokens = tokenize(f"{record.key} {record.value}")
            lexical = (
                len(query_tokens & record_tokens) / len(query_tokens)
                if query_tokens
                else 0.0
            )
            age_days = max(0.0, (timestamp - record.created_at).total_seconds() / 86400)
            recency = math.exp(-math.log(2) * age_days / recency_half_life_days)
            score = (
                0.60 * lexical
                + 0.20 * record.confidence
                + 0.15 * record.importance
                + 0.05 * recency
            )
            if lexical > 0:
                hits.append(MemoryHit(record=record, score=score))

        return sorted(
            hits,
            key=lambda hit: (-hit.score, hit.record.memory_id),
        )[:top_k]

    def forget_key(
        self,
        *,
        owner_id: str,
        namespace: str,
        kind: MemoryKind,
        key: str,
        expected_revision: int | None = None,
    ) -> bool:
        """Redact all retained revisions and remove the active lookup pointer."""

        logical_key = (owner_id, namespace, kind, key)
        active_id = self._active_keys.get(logical_key)
        if active_id is None:
            return False
        active = self._records[active_id]
        if expected_revision is not None and expected_revision != active.revision:
            raise VersionConflict(
                f"expected revision {expected_revision}, found {active.revision}"
            )

        for memory_id, record in list(self._records.items()):
            if (
                record.owner_id,
                record.namespace,
                record.kind,
                record.key,
            ) == logical_key:
                self._records[memory_id] = replace(
                    record,
                    value="[deleted]",
                    source_ref="[deleted]",
                    status="deleted",
                    replaced_by=None,
                )
        del self._active_keys[logical_key]
        return True

    def history(
        self,
        *,
        owner_id: str,
        namespace: str,
        kind: MemoryKind,
        key: str,
    ) -> tuple[MemoryRecord, ...]:
        records = [
            record
            for record in self._records.values()
            if (
                record.owner_id,
                record.namespace,
                record.kind,
                record.key,
            )
            == (owner_id, namespace, kind, key)
        ]
        return tuple(sorted(records, key=lambda record: record.revision))

    def _validate_candidate(
        self, candidate: MemoryCandidate, timestamp: datetime
    ) -> None:
        if not candidate.key.strip() or not candidate.value.strip():
            raise MemoryPolicyError("key and value must not be empty")
        if not candidate.source_ref.strip():
            raise MemoryPolicyError("source provenance is required")
        if not 0 <= candidate.confidence <= 1 or not 0 <= candidate.importance <= 1:
            raise MemoryPolicyError("confidence and importance must be between 0 and 1")
        if candidate.confidence < self._minimum_confidence:
            raise MemoryPolicyError("candidate confidence is below the write threshold")
        if candidate.sensitive and not candidate.user_confirmed:
            raise MemoryPolicyError("sensitive memory requires explicit user confirmation")
        if candidate.kind == "procedural" and not candidate.approved_by:
            raise MemoryPolicyError("procedural memory requires an approver")
        if candidate.expires_at is not None:
            self._require_aware(candidate.expires_at)
            if candidate.expires_at <= timestamp:
                raise MemoryPolicyError("memory must not be expired when committed")
        self._require_aware(timestamp)

    @staticmethod
    def _require_aware(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise MemoryPolicyError("timestamps must be timezone-aware")

    @staticmethod
    def _is_expired(record: MemoryRecord, timestamp: datetime) -> bool:
        return record.expires_at is not None and record.expires_at <= timestamp

    @staticmethod
    def _memory_id(
        logical_key: tuple[str, str, MemoryKind, str], revision: int
    ) -> str:
        payload = repr((logical_key, revision)).encode("utf-8")
        return "mem_" + hashlib.sha256(payload).hexdigest()[:20]

    @staticmethod
    def _operation_fingerprint(
        owner_id: str,
        namespace: str,
        candidate: MemoryCandidate,
        expected_revision: int | None,
    ) -> str:
        payload = repr(
            (owner_id, namespace, candidate, expected_revision)
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def format_memory_context(hits: Sequence[MemoryHit]) -> str:
    """Keep memory IDs and provenance adjacent to injected memory values."""

    return "\n".join(
        f"[{hit.citation}] {hit.record.key}: {hit.record.value} "
        f"(source={hit.record.source_ref})"
        for hit in hits
    )
