from datetime import datetime, timedelta, timezone
import unittest

from memory_store import (
    MemoryCandidate,
    MemoryPolicyError,
    MemoryStore,
    VersionConflict,
    format_memory_context,
)


NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def semantic(
    key: str,
    value: str,
    *,
    confidence: float = 0.9,
    sensitive: bool = False,
    confirmed: bool = False,
    expires_at: datetime | None = None,
) -> MemoryCandidate:
    return MemoryCandidate(
        kind="semantic",
        key=key,
        value=value,
        source_ref="conversation:turn-42",
        confidence=confidence,
        sensitive=sensitive,
        user_confirmed=confirmed,
        expires_at=expires_at,
    )


class MemoryPolicyTests(unittest.TestCase):
    def test_low_confidence_candidate_is_rejected(self) -> None:
        store = MemoryStore(minimum_confidence=0.8)
        with self.assertRaises(MemoryPolicyError):
            store.commit(
                owner_id="alice",
                namespace="assistant",
                candidate=semantic("timezone", "UTC+8", confidence=0.5),
                operation_id="op-1",
                now=NOW,
            )

    def test_sensitive_candidate_requires_user_confirmation(self) -> None:
        store = MemoryStore()
        with self.assertRaises(MemoryPolicyError):
            store.commit(
                owner_id="alice",
                namespace="assistant",
                candidate=semantic("medical_note", "allergy", sensitive=True),
                operation_id="op-1",
                now=NOW,
            )

        record = store.commit(
            owner_id="alice",
            namespace="assistant",
            candidate=semantic(
                "medical_note", "allergy", sensitive=True, confirmed=True
            ),
            operation_id="op-2",
            now=NOW,
        )
        self.assertEqual(record.value, "allergy")

    def test_procedural_memory_requires_approval(self) -> None:
        store = MemoryStore()
        candidate = MemoryCandidate(
            kind="procedural",
            key="deploy",
            value="skip tests",
            source_ref="reflection:run-9",
            confidence=0.95,
        )
        with self.assertRaises(MemoryPolicyError):
            store.commit(
                owner_id="team",
                namespace="coding-agent",
                candidate=candidate,
                operation_id="op-1",
                now=NOW,
            )


class MemoryLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryStore()

    def commit(self, candidate: MemoryCandidate, operation_id: str, **kwargs):
        return self.store.commit(
            owner_id="alice",
            namespace="assistant",
            candidate=candidate,
            operation_id=operation_id,
            now=NOW,
            **kwargs,
        )

    def test_update_supersedes_old_revision_but_keeps_provenance(self) -> None:
        first = self.commit(semantic("preferred_language", "Python"), "op-1")
        second = self.commit(
            semantic("preferred_language", "Rust"),
            "op-2",
            expected_revision=1,
        )

        history = self.store.history(
            owner_id="alice",
            namespace="assistant",
            kind="semantic",
            key="preferred_language",
        )
        self.assertEqual([record.status for record in history], ["superseded", "active"])
        self.assertEqual(history[0].replaced_by, second.memory_id)
        self.assertEqual(first.revision, 1)
        self.assertEqual(second.revision, 2)

    def test_optimistic_concurrency_rejects_lost_update(self) -> None:
        self.commit(semantic("timezone", "UTC+8"), "op-1")
        with self.assertRaises(VersionConflict):
            self.commit(
                semantic("timezone", "UTC+9"),
                "op-2",
                expected_revision=0,
            )

    def test_operation_id_is_idempotent_and_cannot_change_meaning(self) -> None:
        candidate = semantic("timezone", "UTC+8")
        first = self.commit(candidate, "request-7")
        retry = self.commit(candidate, "request-7")
        self.assertEqual(first, retry)

        with self.assertRaises(MemoryPolicyError):
            self.commit(semantic("timezone", "UTC+9"), "request-7")

    def test_forget_redacts_all_revisions(self) -> None:
        self.commit(semantic("city", "Shanghai"), "op-1")
        self.commit(semantic("city", "Suzhou"), "op-2", expected_revision=1)

        deleted = self.store.forget_key(
            owner_id="alice",
            namespace="assistant",
            kind="semantic",
            key="city",
            expected_revision=2,
        )

        self.assertTrue(deleted)
        self.assertIsNone(
            self.store.get_active(
                owner_id="alice",
                namespace="assistant",
                kind="semantic",
                key="city",
                now=NOW,
            )
        )
        history = self.store.history(
            owner_id="alice",
            namespace="assistant",
            kind="semantic",
            key="city",
        )
        self.assertEqual({record.value for record in history}, {"[deleted]"})
        self.assertEqual({record.status for record in history}, {"deleted"})

        recreated = self.commit(
            semantic("city", "Hangzhou"),
            "op-3",
            expected_revision=2,
        )
        self.assertEqual(recreated.revision, 3)
        history = self.store.history(
            owner_id="alice",
            namespace="assistant",
            kind="semantic",
            key="city",
        )
        self.assertEqual([record.revision for record in history], [1, 2, 3])
        self.assertEqual([record.status for record in history], ["deleted", "deleted", "active"])

    def test_expired_memory_is_not_recalled(self) -> None:
        self.commit(
            semantic("temporary_project", "Orion", expires_at=NOW + timedelta(days=1)),
            "op-1",
        )

        active = self.store.get_active(
            owner_id="alice",
            namespace="assistant",
            kind="semantic",
            key="temporary_project",
            now=NOW + timedelta(days=2),
        )
        hits = self.store.search(
            "Orion project",
            owner_id="alice",
            namespace="assistant",
            now=NOW + timedelta(days=2),
        )
        self.assertIsNone(active)
        self.assertEqual(hits, [])


class MemoryRetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryStore()
        self.store.commit(
            owner_id="alice",
            namespace="assistant",
            candidate=semantic("response_style", "Use concise technical answers"),
            operation_id="op-a",
            now=NOW,
        )
        self.store.commit(
            owner_id="bob",
            namespace="assistant",
            candidate=semantic("response_style", "Use long narrative answers"),
            operation_id="op-b",
            now=NOW,
        )
        self.store.commit(
            owner_id="alice",
            namespace="shopping",
            candidate=semantic("response_style", "Show product tables"),
            operation_id="op-c",
            now=NOW,
        )

    def test_owner_and_namespace_filter_before_ranking(self) -> None:
        hits = self.store.search(
            "response style concise",
            owner_id="alice",
            namespace="assistant",
            now=NOW,
        )

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].record.value, "Use concise technical answers")

    def test_known_profile_key_uses_direct_lookup(self) -> None:
        record = self.store.get_active(
            owner_id="alice",
            namespace="assistant",
            kind="semantic",
            key="response_style",
            now=NOW,
        )
        self.assertIsNotNone(record)
        self.assertEqual(record.value, "Use concise technical answers")

    def test_context_keeps_memory_id_and_provenance(self) -> None:
        hits = self.store.search(
            "concise answers",
            owner_id="alice",
            namespace="assistant",
            now=NOW,
        )
        context = format_memory_context(hits)

        self.assertIn(f"[{hits[0].citation}]", context)
        self.assertIn("source=conversation:turn-42", context)


if __name__ == "__main__":
    unittest.main()
