import unittest

from hybrid_retriever import (
    HybridIndex,
    SourceDocument,
    agentic_search,
    chunk_words,
    format_evidence,
    tokenize,
)


CONCEPTS = (
    {"cancel", "cancellation", "terminate"},
    {"order", "purchase"},
    {"refund", "reimburse", "money"},
    {"password", "credential", "login"},
)


def concept_embedder(text: str) -> tuple[float, ...]:
    """A deterministic test double; it is not a real embedding model."""

    tokens = set(tokenize(text))
    return tuple(float(len(tokens & concept)) for concept in CONCEPTS)


def document(
    doc_id: str,
    text: str,
    *,
    tenant: str = "acme",
    version: int = 1,
    principals: frozenset[str] = frozenset({"alice"}),
    metadata: tuple[tuple[str, str], ...] = (("region", "cn"),),
) -> SourceDocument:
    return SourceDocument(
        doc_id=doc_id,
        tenant_id=tenant,
        version=version,
        title=f"Guide {doc_id}",
        text=text,
        allowed_principals=principals,
        metadata=metadata,
    )


class ChunkingTests(unittest.TestCase):
    def test_overlap_repeats_boundary_words(self) -> None:
        chunks = chunk_words("one two three four five six", size=4, overlap=2)
        self.assertEqual(chunks, ["one two three four", "three four five six"])

    def test_invalid_overlap_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            chunk_words("text", size=4, overlap=4)


class HybridIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = HybridIndex(concept_embedder, chunk_size=20, overlap=4)

    def test_tenant_and_acl_filters_run_before_scoring(self) -> None:
        self.index.upsert_document(document("public", "cancel an order", principals=frozenset({"alice"})))
        self.index.upsert_document(document("private", "cancel secret order", principals=frozenset({"bob"})))
        self.index.upsert_document(document("other", "cancel another order", tenant="globex"))

        hits = self.index.search("cancel order", tenant_id="acme", principal="alice")

        self.assertEqual([hit.chunk.doc_id for hit in hits], ["public"])

    def test_metadata_filter_is_applied_before_scoring(self) -> None:
        self.index.upsert_document(document("cn", "refund policy"))
        self.index.upsert_document(
            document("us", "refund policy", metadata=(("region", "us"),))
        )

        hits = self.index.search(
            "refund",
            tenant_id="acme",
            principal="alice",
            filters={"region": "us"},
        )

        self.assertEqual([hit.chunk.doc_id for hit in hits], ["us"])

    def test_lexical_rank_recovers_an_exact_identifier(self) -> None:
        self.index.upsert_document(document("incident", "Runbook for incident ERR-8492"))
        self.index.upsert_document(document("general", "General incident response"))

        hits = self.index.search("ERR-8492", tenant_id="acme", principal="alice")

        self.assertEqual(hits[0].chunk.doc_id, "incident")
        self.assertEqual(hits[0].lexical_rank, 1)

    def test_dense_rank_recovers_a_synonym(self) -> None:
        self.index.upsert_document(document("terminate", "Terminate a purchase in settings"))
        self.index.upsert_document(document("password", "Reset a login credential"))

        hits = self.index.search("cancel order", tenant_id="acme", principal="alice")

        self.assertEqual(hits[0].chunk.doc_id, "terminate")
        self.assertEqual(hits[0].dense_rank, 1)
        self.assertIsNone(hits[0].lexical_rank)

    def test_new_version_replaces_old_chunks(self) -> None:
        self.index.upsert_document(document("policy", "old cancellation policy"))
        self.index.upsert_document(
            document("policy", "new refund policy", version=2)
        )

        old_hits = self.index.search("old", tenant_id="acme", principal="alice")
        new_hits = self.index.search("new refund", tenant_id="acme", principal="alice")

        self.assertEqual(old_hits, [])
        self.assertEqual(new_hits[0].chunk.version, 2)

    def test_stale_update_and_conflicting_same_version_are_rejected(self) -> None:
        self.index.upsert_document(document("policy", "version two", version=2))
        with self.assertRaises(ValueError):
            self.index.upsert_document(document("policy", "version one", version=1))
        with self.assertRaises(ValueError):
            self.index.upsert_document(document("policy", "different version two", version=2))

    def test_delete_removes_every_chunk_and_checks_version(self) -> None:
        self.index.upsert_document(
            document("long", " ".join(f"word{i}" for i in range(45)), version=3)
        )
        with self.assertRaises(ValueError):
            self.index.delete_document("acme", "long", expected_version=2)

        self.assertTrue(self.index.delete_document("acme", "long", expected_version=3))
        self.assertEqual(
            self.index.search("word1", tenant_id="acme", principal="alice"),
            [],
        )

    def test_evidence_keeps_citation_adjacent_to_text(self) -> None:
        self.index.upsert_document(document("refund", "Refunds take five days"))
        hits = self.index.search("refund", tenant_id="acme", principal="alice")

        evidence = format_evidence(hits)

        self.assertIn(f"[{hits[0].citation}]", evidence)
        self.assertIn("Refunds take five days", evidence)


class AgenticSearchTests(unittest.TestCase):
    def test_loop_stops_on_duplicate_query(self) -> None:
        index = HybridIndex(concept_embedder)
        index.upsert_document(document("order", "cancel an order"))

        steps = agentic_search(
            index,
            "cancel order",
            tenant_id="acme",
            principal="alice",
            plan_next=lambda _: "Cancel   order",
            max_steps=5,
        )

        self.assertEqual(len(steps), 1)

    def test_loop_obeys_maximum_step_budget(self) -> None:
        index = HybridIndex(concept_embedder)
        index.upsert_document(document("order", "cancel order refund"))

        steps = agentic_search(
            index,
            "query one",
            tenant_id="acme",
            principal="alice",
            plan_next=lambda history: f"query {len(history) + 1}",
            max_steps=3,
        )

        self.assertEqual([step.query for step in steps], ["query one", "query 2", "query 3"])


if __name__ == "__main__":
    unittest.main()
