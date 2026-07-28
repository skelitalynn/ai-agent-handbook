"""A small, dependency-free retrieval pipeline for Chapter 10.

The implementation makes four boundaries explicit:

1. authorization filters run before scoring;
2. document replacement is versioned and atomic within this in-memory store;
3. lexical and dense ranks are fused without comparing incompatible raw scores;
4. agentic search has query, step, and duplicate-query termination controls.

The injected embedder is deliberately separate from the index.  Production systems
should use a real embedding model and durable indexes instead of the toy embedder in
the accompanying tests.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import math
import re
from typing import Callable, Iterable, Mapping, Sequence


Embedder = Callable[[str], Sequence[float]]
TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Return a deterministic teaching tokenizer, not a production segmenter."""

    return TOKEN_PATTERN.findall(text.casefold())


def chunk_words(text: str, *, size: int = 80, overlap: int = 16) -> list[str]:
    """Split text into overlapping word windows."""

    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must satisfy 0 <= overlap < size")

    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    step = size - overlap
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start : start + size]))
        if start + size >= len(words):
            break
    return chunks


def _normalize(vector: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(value) for value in vector)
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        return values
    return tuple(value / norm for value in values)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions do not match")
    return sum(a * b for a, b in zip(left, right))


@dataclass(frozen=True)
class SourceDocument:
    doc_id: str
    tenant_id: str
    version: int
    title: str
    text: str
    allowed_principals: frozenset[str]
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    tenant_id: str
    version: int
    title: str
    text: str
    allowed_principals: frozenset[str]
    metadata: tuple[tuple[str, str], ...]
    tokens: tuple[str, ...]
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class SearchHit:
    chunk: Chunk
    fused_score: float
    lexical_rank: int | None
    dense_rank: int | None

    @property
    def citation(self) -> str:
        return self.chunk.chunk_id


@dataclass(frozen=True)
class SearchStep:
    query: str
    hits: tuple[SearchHit, ...]


class HybridIndex:
    """An in-memory hybrid index with tenant and principal isolation."""

    def __init__(self, embedder: Embedder, *, chunk_size: int = 80, overlap: int = 16):
        self._embedder = embedder
        self._chunk_size = chunk_size
        self._overlap = overlap
        self._chunks: dict[str, Chunk] = {}
        self._versions: dict[tuple[str, str], int] = {}
        self._fingerprints: dict[tuple[str, str], str] = {}

    def upsert_document(self, document: SourceDocument) -> None:
        """Insert or replace one document after validating its version.

        New chunks are fully built before the visible index is changed.  The method
        therefore models an atomic replacement inside this single-process example.
        """

        if document.version < 1:
            raise ValueError("version must be positive")
        if not document.allowed_principals:
            raise ValueError("allowed_principals must not be empty")

        key = (document.tenant_id, document.doc_id)
        fingerprint = self._fingerprint(document)
        current_version = self._versions.get(key)
        if current_version is not None:
            if document.version < current_version:
                raise ValueError("stale document version")
            if document.version == current_version:
                if fingerprint == self._fingerprints[key]:
                    return
                raise ValueError("same version has different content or access policy")

        new_chunks = self._build_chunks(document)
        old_ids = [
            chunk_id
            for chunk_id, chunk in self._chunks.items()
            if (chunk.tenant_id, chunk.doc_id) == key
        ]
        for chunk_id in old_ids:
            del self._chunks[chunk_id]
        self._chunks.update({chunk.chunk_id: chunk for chunk in new_chunks})
        self._versions[key] = document.version
        self._fingerprints[key] = fingerprint

    def delete_document(
        self,
        tenant_id: str,
        doc_id: str,
        *,
        expected_version: int | None = None,
    ) -> bool:
        """Delete all chunks, optionally rejecting a stale delete command."""

        key = (tenant_id, doc_id)
        current_version = self._versions.get(key)
        if current_version is None:
            return False
        if expected_version is not None and expected_version != current_version:
            raise ValueError("delete version does not match current document")

        for chunk_id in [
            chunk_id
            for chunk_id, chunk in self._chunks.items()
            if (chunk.tenant_id, chunk.doc_id) == key
        ]:
            del self._chunks[chunk_id]
        del self._versions[key]
        del self._fingerprints[key]
        return True

    def search(
        self,
        query: str,
        *,
        tenant_id: str,
        principal: str,
        top_k: int = 5,
        filters: Mapping[str, str] | None = None,
        rrf_k: int = 60,
    ) -> list[SearchHit]:
        """Run authorized hybrid retrieval using reciprocal rank fusion."""

        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if rrf_k <= 0:
            raise ValueError("rrf_k must be positive")

        # This is a security boundary: unauthorized chunks never enter either scorer.
        candidates = [
            chunk
            for chunk in self._chunks.values()
            if chunk.tenant_id == tenant_id
            and (principal in chunk.allowed_principals or "*" in chunk.allowed_principals)
            and self._matches_filters(chunk, filters or {})
        ]
        if not candidates:
            return []

        query_tokens = tokenize(query)
        lexical_scores = self._bm25(query_tokens, candidates)
        query_embedding = _normalize(self._embedder(query))
        dense_scores = {
            chunk.chunk_id: _cosine(query_embedding, chunk.embedding)
            for chunk in candidates
        }

        lexical_ranks = self._positive_ranks(lexical_scores)
        dense_ranks = self._positive_ranks(dense_scores)
        fused: dict[str, float] = {}
        for chunk in candidates:
            score = 0.0
            if chunk.chunk_id in lexical_ranks:
                score += 1.0 / (rrf_k + lexical_ranks[chunk.chunk_id])
            if chunk.chunk_id in dense_ranks:
                score += 1.0 / (rrf_k + dense_ranks[chunk.chunk_id])
            if score > 0:
                fused[chunk.chunk_id] = score

        ordered_ids = sorted(
            fused,
            key=lambda chunk_id: (-fused[chunk_id], chunk_id),
        )[:top_k]
        return [
            SearchHit(
                chunk=self._chunks[chunk_id],
                fused_score=fused[chunk_id],
                lexical_rank=lexical_ranks.get(chunk_id),
                dense_rank=dense_ranks.get(chunk_id),
            )
            for chunk_id in ordered_ids
        ]

    def _build_chunks(self, document: SourceDocument) -> list[Chunk]:
        parts = chunk_words(
            document.text,
            size=self._chunk_size,
            overlap=self._overlap,
        )
        result: list[Chunk] = []
        for part_number, text in enumerate(parts):
            contextual_text = f"{document.title}\n{text}"
            chunk_id = (
                f"{document.tenant_id}:{document.doc_id}:"
                f"v{document.version}:p{part_number}"
            )
            result.append(
                Chunk(
                    chunk_id=chunk_id,
                    doc_id=document.doc_id,
                    tenant_id=document.tenant_id,
                    version=document.version,
                    title=document.title,
                    text=text,
                    allowed_principals=document.allowed_principals,
                    metadata=document.metadata,
                    tokens=tuple(tokenize(contextual_text)),
                    embedding=_normalize(self._embedder(contextual_text)),
                )
            )
        return result

    @staticmethod
    def _matches_filters(chunk: Chunk, filters: Mapping[str, str]) -> bool:
        metadata = dict(chunk.metadata)
        return all(metadata.get(key) == value for key, value in filters.items())

    @staticmethod
    def _fingerprint(document: SourceDocument) -> str:
        payload = repr(
            (
                document.title,
                document.text,
                sorted(document.allowed_principals),
                sorted(document.metadata),
            )
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _positive_ranks(scores: Mapping[str, float]) -> dict[str, int]:
        ordered = sorted(
            ((chunk_id, score) for chunk_id, score in scores.items() if score > 0),
            key=lambda item: (-item[1], item[0]),
        )
        return {chunk_id: rank for rank, (chunk_id, _) in enumerate(ordered, start=1)}

    @staticmethod
    def _bm25(query_tokens: Iterable[str], chunks: Sequence[Chunk]) -> dict[str, float]:
        query_terms = set(query_tokens)
        if not query_terms:
            return {chunk.chunk_id: 0.0 for chunk in chunks}

        frequencies = {chunk.chunk_id: Counter(chunk.tokens) for chunk in chunks}
        lengths = {chunk.chunk_id: len(chunk.tokens) for chunk in chunks}
        average_length = sum(lengths.values()) / len(chunks) or 1.0
        document_frequency = {
            term: sum(term in frequencies[chunk.chunk_id] for chunk in chunks)
            for term in query_terms
        }

        k1 = 1.2
        b = 0.75
        scores: dict[str, float] = {}
        for chunk in chunks:
            score = 0.0
            term_counts = frequencies[chunk.chunk_id]
            for term in query_terms:
                frequency = term_counts[term]
                if frequency == 0:
                    continue
                df = document_frequency[term]
                idf = math.log(1.0 + (len(chunks) - df + 0.5) / (df + 0.5))
                denominator = frequency + k1 * (
                    1.0 - b + b * lengths[chunk.chunk_id] / average_length
                )
                score += idf * frequency * (k1 + 1.0) / denominator
            scores[chunk.chunk_id] = score
        return scores


def agentic_search(
    index: HybridIndex,
    initial_query: str,
    *,
    tenant_id: str,
    principal: str,
    plan_next: Callable[[tuple[SearchStep, ...]], str | None],
    top_k: int = 5,
    max_steps: int = 3,
) -> tuple[SearchStep, ...]:
    """Iteratively search while enforcing a deterministic outer-loop budget.

    ``plan_next`` may call a model in a real system.  It returns ``None`` when the
    evidence is sufficient.  Repeated normalized queries terminate the loop.
    """

    if max_steps <= 0:
        raise ValueError("max_steps must be positive")

    steps: list[SearchStep] = []
    seen_queries: set[str] = set()
    query: str | None = initial_query
    while query is not None and len(steps) < max_steps:
        normalized = " ".join(tokenize(query))
        if not normalized or normalized in seen_queries:
            break
        seen_queries.add(normalized)
        hits = tuple(
            index.search(
                query,
                tenant_id=tenant_id,
                principal=principal,
                top_k=top_k,
            )
        )
        steps.append(SearchStep(query=query, hits=hits))
        query = plan_next(tuple(steps))
    return tuple(steps)


def format_evidence(hits: Sequence[SearchHit]) -> str:
    """Create an evidence block that keeps stable citations next to content."""

    return "\n\n".join(
        f"[{hit.citation}] {hit.chunk.title}\n{hit.chunk.text}" for hit in hits
    )
