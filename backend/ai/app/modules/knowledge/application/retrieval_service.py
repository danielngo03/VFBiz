import hashlib
import math
import re
from collections.abc import Callable
from datetime import UTC, datetime

from app.modules.knowledge.application.retrieval_ports import (
    CandidateReranker,
    QueryEmbedder,
    RetrievalBackendUnavailable,
    RetrievalCandidateSearcher,
    RetrievalSnapshotResolver,
)
from app.modules.knowledge.domain import KnowledgeScope
from app.modules.knowledge.domain.retrieval import (
    RetrievalCandidate,
    RetrievalCandidateQuery,
    RetrievalResult,
    RetrievalSnapshot,
    RetrievalStatus,
    RetrievedEvidence,
    SnapshotStatus,
)

_TOKEN_PATTERN = re.compile(r"[^\W_]+", flags=re.UNICODE)


class KnowledgeRetrievalService:
    """Revision-coherent hybrid retrieval with fail-closed profile isolation."""

    def __init__(
        self,
        snapshots: RetrievalSnapshotResolver,
        candidates: RetrievalCandidateSearcher,
        embedder: QueryEmbedder,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_candidates: int = 200,
        max_results: int = 8,
        reranker: CandidateReranker | None = None,
        max_rerank_candidates: int = 40,
        lexical_weight: float = 0.35,
        minimum_score: float = 0.05,
    ) -> None:
        if not 1 <= max_results <= max_candidates <= 1_000:
            raise ValueError("retrieval result and candidate limits are invalid")
        if not max_results <= max_rerank_candidates <= max_candidates:
            raise ValueError("reranker window must cover results within candidate limit")
        if not 0.0 <= lexical_weight <= 1.0:
            raise ValueError("lexical weight must be between zero and one")
        if not 0.0 <= minimum_score <= 1.0:
            raise ValueError("minimum retrieval score must be between zero and one")
        self._snapshots = snapshots
        self._candidates = candidates
        self._embedder = embedder
        self._clock = clock
        self._max_candidates = max_candidates
        self._max_results = max_results
        self._reranker = reranker
        self._max_rerank_candidates = max_rerank_candidates
        self._lexical_weight = lexical_weight
        self._minimum_score = minimum_score

    async def retrieve(
        self,
        *,
        query: str,
        scope: KnowledgeScope,
        authorized_acl_namespaces: frozenset[str],
    ) -> RetrievalResult:
        normalized_query = " ".join(query.split())
        if not normalized_query or len(normalized_query) > 4_000:
            return _outcome(RetrievalStatus.NO_APPROVED_EVIDENCE, "INVALID_QUERY")
        if scope.acl_namespace not in authorized_acl_namespaces:
            return _outcome(RetrievalStatus.KNOWLEDGE_UNAVAILABLE, "ACL_SCOPE_DENIED")

        try:
            resolution = await self._snapshots.resolve(scope)
        except RetrievalBackendUnavailable:
            return _outcome(RetrievalStatus.KNOWLEDGE_UNAVAILABLE, "SNAPSHOT_STORE_UNAVAILABLE")

        if resolution.status is SnapshotStatus.UPDATING:
            return _outcome(RetrievalStatus.KNOWLEDGE_UPDATING, resolution.reason)
        if resolution.status is SnapshotStatus.BLOCKED:
            return _outcome(RetrievalStatus.KNOWLEDGE_UNAVAILABLE, resolution.reason)
        if resolution.status is SnapshotStatus.MISSING:
            return _outcome(RetrievalStatus.NO_APPROVED_EVIDENCE, resolution.reason)
        snapshot = resolution.snapshot
        if snapshot is None:
            return _outcome(RetrievalStatus.KNOWLEDGE_UNAVAILABLE, "INVALID_SNAPSHOT_STATE")

        current_time = self._clock()
        if current_time.tzinfo is None:
            raise ValueError("retrieval clock must include a timezone")
        if snapshot.effective_at > current_time:
            return _pinned_outcome(snapshot, RetrievalStatus.NO_APPROVED_EVIDENCE, "NOT_EFFECTIVE")
        if snapshot.freshness_expires_at <= current_time:
            return _pinned_outcome(
                snapshot,
                RetrievalStatus.KNOWLEDGE_UNAVAILABLE,
                "ACTIVE_RELEASE_STALE",
            )
        if (
            snapshot.embedding_revision != self._embedder.revision
            or snapshot.embedding_dimension != self._embedder.dimension
        ):
            return _pinned_outcome(
                snapshot,
                RetrievalStatus.KNOWLEDGE_UNAVAILABLE,
                "EMBEDDING_RUNTIME_MISMATCH",
            )
        if (
            self._reranker is not None
            and self._reranker.retriever_revision != snapshot.retriever_revision
        ):
            return _pinned_outcome(
                snapshot,
                RetrievalStatus.KNOWLEDGE_UNAVAILABLE,
                "RERANKER_RUNTIME_MISMATCH",
            )

        try:
            query_embedding = await self._embedder.embed_query(normalized_query)
        except RetrievalBackendUnavailable:
            return _pinned_outcome(
                snapshot,
                RetrievalStatus.KNOWLEDGE_UNAVAILABLE,
                "EMBEDDING_RUNTIME_UNAVAILABLE",
            )
        if not _valid_vector(query_embedding, snapshot.embedding_dimension):
            return _pinned_outcome(
                snapshot,
                RetrievalStatus.KNOWLEDGE_UNAVAILABLE,
                "INVALID_QUERY_EMBEDDING",
            )

        try:
            candidates = await self._candidates.search_candidates(
                snapshot,
                authorized_acl_namespaces=authorized_acl_namespaces,
                query=RetrievalCandidateQuery(
                    normalized_text=normalized_query,
                    embedding=query_embedding,
                    candidate_limit=self._max_candidates,
                    lexical_weight=self._lexical_weight,
                ),
            )
        except RetrievalBackendUnavailable:
            return _pinned_outcome(
                snapshot,
                RetrievalStatus.KNOWLEDGE_UNAVAILABLE,
                "INDEX_UNAVAILABLE",
            )

        eligible = tuple(
            candidate
            for candidate in candidates
            if _candidate_is_authorized(candidate, snapshot, authorized_acl_namespaces)
            and _valid_vector(candidate.embedding, snapshot.embedding_dimension)
        )
        if not eligible:
            return _pinned_outcome(
                snapshot,
                RetrievalStatus.NO_APPROVED_EVIDENCE,
                "NO_MATCHING_EVIDENCE",
            )

        query_tokens = _tokens(normalized_query)
        ranked = sorted(
            (
                (
                    _hybrid_score(
                        query_tokens,
                        query_embedding,
                        candidate,
                        lexical_weight=self._lexical_weight,
                    ),
                    candidate,
                )
                for candidate in eligible
            ),
            key=lambda item: (-item[0], str(item[1].chunk_id)),
        )
        final_ranked = ranked
        if self._reranker is not None:
            rerank_window = tuple(
                candidate for _, candidate in ranked[: self._max_rerank_candidates]
            )
            try:
                rerank_scores = await self._reranker.rerank(
                    normalized_query,
                    rerank_window,
                )
            except RetrievalBackendUnavailable:
                return _pinned_outcome(
                    snapshot,
                    RetrievalStatus.KNOWLEDGE_UNAVAILABLE,
                    "RERANKER_RUNTIME_UNAVAILABLE",
                )
            expected_ids = {candidate.chunk_id for candidate in rerank_window}
            received_ids = [item.chunk_id for item in rerank_scores]
            if (
                len(received_ids) != len(expected_ids)
                or len(set(received_ids)) != len(received_ids)
                or set(received_ids) != expected_ids
            ):
                return _pinned_outcome(
                    snapshot,
                    RetrievalStatus.KNOWLEDGE_UNAVAILABLE,
                    "INVALID_RERANK_RESULT",
                )
            candidates_by_id = {candidate.chunk_id: candidate for candidate in rerank_window}
            final_ranked = sorted(
                ((item.score, candidates_by_id[item.chunk_id]) for item in rerank_scores),
                key=lambda item: (-item[0], str(item[1].chunk_id)),
            )

        evidence = tuple(
            _to_evidence(snapshot, candidate, score)
            for score, candidate in final_ranked[: self._max_results]
            if score >= self._minimum_score
        )
        if not evidence:
            return _pinned_outcome(
                snapshot,
                RetrievalStatus.NO_APPROVED_EVIDENCE,
                "BELOW_RETRIEVAL_THRESHOLD",
            )
        return RetrievalResult(
            status=RetrievalStatus.EVIDENCE,
            reason="APPROVED_EVIDENCE_FOUND",
            release_id=snapshot.release_id,
            pointer_version=snapshot.pointer_version,
            evidence=evidence,
        )


def _candidate_is_authorized(
    candidate: RetrievalCandidate,
    snapshot: RetrievalSnapshot,
    authorized_acl_namespaces: frozenset[str],
) -> bool:
    return (
        candidate.release_id == snapshot.release_id
        and candidate.source_id in snapshot.source_ids
        and candidate.source_revision == snapshot.source_revision_for(candidate.source_id)
        and candidate.acl_namespace == snapshot.scope.acl_namespace
        and candidate.acl_namespace in authorized_acl_namespaces
        and candidate.embedding_revision == snapshot.embedding_revision
    )


def _hybrid_score(
    query_tokens: frozenset[str],
    query_embedding: tuple[float, ...],
    candidate: RetrievalCandidate,
    *,
    lexical_weight: float,
) -> float:
    candidate_tokens = _tokens(candidate.excerpt)
    lexical = len(query_tokens & candidate_tokens) / len(query_tokens) if query_tokens else 0.0
    cosine = _cosine_similarity(query_embedding, candidate.embedding)
    vector = (cosine + 1.0) / 2.0
    return min(1.0, max(0.0, lexical_weight * lexical + (1.0 - lexical_weight) * vector))


def _cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return -1.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def _tokens(value: str) -> frozenset[str]:
    return frozenset(match.group(0).casefold() for match in _TOKEN_PATTERN.finditer(value))


def _valid_vector(vector: tuple[float, ...], dimension: int) -> bool:
    return (
        len(vector) == dimension
        and any(value != 0.0 for value in vector)
        and all(math.isfinite(value) for value in vector)
    )


def _to_evidence(
    snapshot: RetrievalSnapshot,
    candidate: RetrievalCandidate,
    score: float,
) -> RetrievedEvidence:
    evidence_id = hashlib.sha256(
        (
            f"{snapshot.release_id}:{candidate.chunk_id}:"
            f"{candidate.source_revision}:{candidate.content_checksum}"
        ).encode()
    ).hexdigest()
    return RetrievedEvidence(
        evidence_id=evidence_id,
        release_id=snapshot.release_id,
        pointer_version=snapshot.pointer_version,
        source_id=candidate.source_id,
        source_uri=candidate.source_uri,
        source_revision=candidate.source_revision,
        title=candidate.title,
        excerpt=candidate.excerpt,
        freshness=snapshot.freshness_expires_at,
        score=score,
    )


def _outcome(status: RetrievalStatus, reason: str) -> RetrievalResult:
    return RetrievalResult(status=status, reason=reason)


def _pinned_outcome(
    snapshot: RetrievalSnapshot,
    status: RetrievalStatus,
    reason: str,
) -> RetrievalResult:
    return RetrievalResult(
        status=status,
        reason=reason,
        release_id=snapshot.release_id,
        pointer_version=snapshot.pointer_version,
    )
