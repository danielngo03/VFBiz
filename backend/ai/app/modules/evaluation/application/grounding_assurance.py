import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from time import monotonic
from typing import Protocol


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


class AnswerSegmentKind(StrEnum):
    FACTUAL = "factual"
    DISCOURSE = "discourse"
    REFUSAL = "refusal"


@dataclass(frozen=True, slots=True)
class AnswerSegment:
    segment_id: str
    kind: AnswerSegmentKind
    text: str
    citation_ids: tuple[str, ...] = ()
    template_id: str | None = None

    def __post_init__(self) -> None:
        if (
            not self.segment_id.strip()
            or len(self.segment_id) > 128
            or not self.text.strip()
            or len(self.text) > 2_000
        ):
            raise ValueError("answer segment must be non-empty and bounded")
        if self.kind is AnswerSegmentKind.FACTUAL:
            if not self.citation_ids or self.template_id is not None:
                raise ValueError("factual answer segment must be cited and generated")
        elif self.citation_ids or not self.template_id:
            raise ValueError("non-factual answer segment must reference a safe template")
        if len(self.citation_ids) > 8 or len(set(self.citation_ids)) != len(
            self.citation_ids
        ):
            raise ValueError("answer segment citations must be unique and bounded")


@dataclass(frozen=True, slots=True)
class SegmentedAnswer:
    segments: tuple[AnswerSegment, ...]

    def __post_init__(self) -> None:
        if (
            not self.segments
            or len(self.segments) > 32
            or len({item.segment_id for item in self.segments}) != len(self.segments)
        ):
            raise ValueError("answer segments must be non-empty, unique and bounded")

    @property
    def rendered_text(self) -> str:
        return "\n".join(item.text for item in self.segments)

    @property
    def factual_claims(self) -> tuple["FactualClaim", ...]:
        return tuple(
            FactualClaim(item.segment_id, item.text, item.citation_ids)
            for item in self.segments
            if item.kind is AnswerSegmentKind.FACTUAL
        )


@dataclass(frozen=True, slots=True)
class FactualClaim:
    claim_id: str
    text: str
    citation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CitationEvidence:
    evidence_id: str
    excerpt: str
    source_uri: str
    source_revision: str
    knowledge_revision: str
    effective_at: datetime
    expires_at: datetime | None
    content_sha256: str

    def __post_init__(self) -> None:
        if any(
            not value.strip() or len(value) > 512
            for value in (
                self.evidence_id,
                self.source_uri,
                self.source_revision,
                self.knowledge_revision,
            )
        ):
            raise ValueError("citation evidence identity must be bounded")
        if not self.excerpt.strip() or len(self.excerpt) > 16_000:
            raise ValueError("citation evidence excerpt must be non-empty and bounded")
        if self.effective_at.tzinfo is None or (
            self.expires_at is not None and self.expires_at.tzinfo is None
        ):
            raise ValueError("evidence effective window must include timezone")
        if not _is_sha256(self.content_sha256):
            raise ValueError("evidence content digest must use SHA-256 hex")


@dataclass(frozen=True, slots=True)
class TrustedRetrievalSnapshot:
    snapshot_id: str
    release_id: str
    pointer_revision: int
    assistant_profile: str
    acl_namespace: str
    retriever_revision: str
    knowledge_revision: str
    evidence: tuple[CitationEvidence, ...]

    def __post_init__(self) -> None:
        if (
            any(
                not value.strip() or len(value) > 160
                for value in (
                    self.snapshot_id,
                    self.release_id,
                    self.assistant_profile,
                    self.acl_namespace,
                    self.retriever_revision,
                    self.knowledge_revision,
                )
            )
            or self.pointer_revision < 1
            or not self.evidence
            or len(self.evidence) > 32
            or len({item.evidence_id for item in self.evidence}) != len(self.evidence)
        ):
            raise ValueError("trusted retrieval snapshot must be unique and bounded")

    @property
    def content_sha256(self) -> str:
        payload = {
            "aclNamespace": self.acl_namespace,
            "assistantProfile": self.assistant_profile,
            "evidence": [
                {
                    "contentSha256": item.content_sha256,
                    "effectiveAt": item.effective_at.isoformat(),
                    "evidenceId": item.evidence_id,
                    "excerpt": item.excerpt,
                    "expiresAt": item.expires_at.isoformat() if item.expires_at else None,
                    "knowledgeRevision": item.knowledge_revision,
                    "sourceRevision": item.source_revision,
                    "sourceUri": item.source_uri,
                }
                for item in sorted(self.evidence, key=lambda value: value.evidence_id)
            ],
            "knowledgeRevision": self.knowledge_revision,
            "pointerRevision": self.pointer_revision,
            "releaseId": self.release_id,
            "retrieverRevision": self.retriever_revision,
            "snapshotId": self.snapshot_id,
        }
        canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        return sha256(canonical.encode()).hexdigest()


class RetrievalSnapshotAuthority(Protocol):
    async def resolve(
        self,
        snapshot_id: str,
        context: "GroundingPolicyContext",
    ) -> TrustedRetrievalSnapshot | None: ...


@dataclass(frozen=True, slots=True)
class GroundingPolicyContext:
    context_id: str
    activation_id: str
    candidate_sha256: str
    assistant_profile: str
    authorization_context_sha256: str
    retriever_revision: str
    knowledge_revision: str
    active_pointer_revision: int

    def __post_init__(self) -> None:
        if (
            any(
                not value.strip() or len(value) > 160
                for value in (
                    self.context_id,
                    self.activation_id,
                    self.assistant_profile,
                    self.retriever_revision,
                    self.knowledge_revision,
                )
            )
            or not _is_sha256(self.candidate_sha256)
            or not _is_sha256(self.authorization_context_sha256)
            or self.active_pointer_revision < 1
        ):
            raise ValueError("grounding policy context must be trusted and bounded")


class GroundingPolicyContextAuthority(Protocol):
    async def resolve(self, context_id: str) -> GroundingPolicyContext | None: ...


class SafeTemplateRegistry(Protocol):
    def exact_text(self, template_id: str) -> str | None: ...


@dataclass(frozen=True, slots=True)
class ClaimEntailmentDecision:
    supported: bool
    score: float
    engine_revision: str


class ClaimEntailmentEngine(Protocol):
    @property
    def revision(self) -> str: ...

    async def evaluate(
        self, claim: FactualClaim, evidence: CitationEvidence
    ) -> ClaimEntailmentDecision: ...


class ExactEvidenceEntailmentEngine:
    revision = "exact-evidence-v2"

    async def evaluate(
        self, claim: FactualClaim, evidence: CitationEvidence
    ) -> ClaimEntailmentDecision:
        supported = " ".join(claim.text.casefold().split()) == " ".join(
            evidence.excerpt.casefold().split()
        )
        return ClaimEntailmentDecision(supported, 1.0 if supported else 0.0, self.revision)


@dataclass(frozen=True, slots=True)
class GroundingAssuranceRequest:
    answer: SegmentedAnswer
    policy_context_id: str
    snapshot_id: str
    expected_snapshot_sha256: str
    expected_validator_revision: str
    deadline_seconds: float = 2.0
    max_entailment_calls: int = 24

    def __post_init__(self) -> None:
        if (
            any(
                not value.strip() or len(value) > 160
                for value in (
                    self.policy_context_id,
                    self.snapshot_id,
                    self.expected_validator_revision,
                )
            )
            or not _is_sha256(self.expected_snapshot_sha256)
            or not 0 < self.deadline_seconds <= 10
            or not 1 <= self.max_entailment_calls <= 64
        ):
            raise ValueError("grounding request identity and budget must be bounded")


@dataclass(frozen=True, slots=True)
class GroundingAssuranceResult:
    supported: bool
    validator_revision: str
    evidence_snapshot_sha256: str
    rendered_text_sha256: str
    unsupported_claim_ids: tuple[str, ...]
    failure_codes: tuple[str, ...]


class GroundingAssuranceValidator:
    def __init__(
        self,
        *,
        engine: ClaimEntailmentEngine,
        policy_context_authority: GroundingPolicyContextAuthority,
        snapshot_authority: RetrievalSnapshotAuthority,
        template_registry: SafeTemplateRegistry,
        minimum_score: float,
        clock: Callable[[], datetime],
    ) -> None:
        if not 0 < minimum_score <= 1:
            raise ValueError("minimum grounding score must be in (0, 1]")
        self._engine = engine
        self._contexts = policy_context_authority
        self._snapshots = snapshot_authority
        self._templates = template_registry
        self._minimum_score = minimum_score
        self._clock = clock

    async def validate(self, request: GroundingAssuranceRequest) -> GroundingAssuranceResult:
        empty_digest = "0" * 64
        if self._engine.revision != request.expected_validator_revision:
            return self._failed(request, empty_digest, ("VALIDATOR_REVISION_MISMATCH",))
        deadline = monotonic() + request.deadline_seconds
        context = await self._resolve_context(request, deadline)
        if context is None:
            return self._failed(request, empty_digest, ("POLICY_CONTEXT_NOT_FOUND",))
        snapshot = await self._resolve_snapshot(request, context, deadline)
        if snapshot is None:
            return self._failed(request, empty_digest, ("SNAPSHOT_NOT_FOUND",))
        observed_digest = snapshot.content_sha256
        identity_failures = self._snapshot_identity_failures(request, context, snapshot)
        if identity_failures:
            return self._failed(request, observed_digest, identity_failures)
        evidence_failures = self._evidence_failures(snapshot)
        if evidence_failures:
            return self._failed(request, observed_digest, evidence_failures)
        if not self._safe_non_factual_segments(request.answer):
            return self._failed(request, observed_digest, ("UNSAFE_NON_FACTUAL_SEGMENT",))

        evidence_by_id = {item.evidence_id: item for item in snapshot.evidence}
        unsupported: list[str] = []
        calls = 0
        for claim in request.answer.factual_claims:
            cited = [evidence_by_id.get(item) for item in claim.citation_ids]
            if any(item is None for item in cited):
                unsupported.append(claim.claim_id)
                continue
            claim_supported = False
            for evidence in cited:
                if evidence is None or calls >= request.max_entailment_calls:
                    return self._failed(request, observed_digest, ("VALIDATION_BUDGET_EXHAUSTED",))
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return self._failed(request, observed_digest, ("VALIDATION_DEADLINE_EXCEEDED",))
                calls += 1
                try:
                    decision = await asyncio.wait_for(
                        self._engine.evaluate(claim, evidence), timeout=remaining
                    )
                except TimeoutError:
                    return self._failed(
                        request, observed_digest, ("VALIDATION_DEADLINE_EXCEEDED",)
                    )
                except Exception:
                    return self._failed(request, observed_digest, ("VALIDATOR_UNAVAILABLE",))
                if (
                    decision.engine_revision == request.expected_validator_revision
                    and decision.supported
                    and decision.score >= self._minimum_score
                ):
                    claim_supported = True
                    break
            if not claim_supported:
                unsupported.append(claim.claim_id)
        return self._result(
            request,
            observed_digest,
            supported=not unsupported,
            unsupported=tuple(unsupported),
            failures=() if not unsupported else ("UNSUPPORTED_CLAIM",),
        )

    def _snapshot_identity_failures(
        self,
        request: GroundingAssuranceRequest,
        context: GroundingPolicyContext,
        snapshot: TrustedRetrievalSnapshot,
    ) -> tuple[str, ...]:
        failures: list[str] = []
        if snapshot.content_sha256 != request.expected_snapshot_sha256:
            failures.append("EVIDENCE_SNAPSHOT_MISMATCH")
        if snapshot.release_id != context.activation_id:
            failures.append("RELEASE_ID_MISMATCH")
        if snapshot.assistant_profile != context.assistant_profile:
            failures.append("ASSISTANT_PROFILE_MISMATCH")
        if sha256(snapshot.acl_namespace.encode()).hexdigest() != (
            context.authorization_context_sha256
        ):
            failures.append("AUTHORIZATION_CONTEXT_MISMATCH")
        if snapshot.retriever_revision != context.retriever_revision:
            failures.append("RETRIEVER_REVISION_MISMATCH")
        if snapshot.knowledge_revision != context.knowledge_revision:
            failures.append("KNOWLEDGE_REVISION_MISMATCH")
        if snapshot.pointer_revision != context.active_pointer_revision:
            failures.append("POINTER_REVISION_MISMATCH")
        return tuple(failures)

    async def _resolve_context(
        self,
        request: GroundingAssuranceRequest,
        deadline: float,
    ) -> GroundingPolicyContext | None:
        remaining = deadline - monotonic()
        if remaining <= 0:
            return None
        try:
            return await asyncio.wait_for(
                self._contexts.resolve(request.policy_context_id),
                timeout=remaining,
            )
        except (TimeoutError, Exception):
            return None

    async def _resolve_snapshot(
        self,
        request: GroundingAssuranceRequest,
        context: GroundingPolicyContext,
        deadline: float,
    ) -> TrustedRetrievalSnapshot | None:
        remaining = deadline - monotonic()
        if remaining <= 0:
            return None
        try:
            return await asyncio.wait_for(
                self._snapshots.resolve(request.snapshot_id, context),
                timeout=remaining,
            )
        except (TimeoutError, Exception):
            return None

    def _evidence_failures(self, snapshot: TrustedRetrievalSnapshot) -> tuple[str, ...]:
        now = self._clock()
        failures: list[str] = []
        for item in snapshot.evidence:
            if sha256(item.excerpt.encode()).hexdigest() != item.content_sha256:
                failures.append("EVIDENCE_CONTENT_DIGEST_MISMATCH")
            if item.knowledge_revision != snapshot.knowledge_revision:
                failures.append("EVIDENCE_REVISION_MISMATCH")
            if now < item.effective_at:
                failures.append("EVIDENCE_NOT_EFFECTIVE")
            if item.expires_at is not None and now >= item.expires_at:
                failures.append("EVIDENCE_EXPIRED")
        return tuple(dict.fromkeys(failures))

    def _safe_non_factual_segments(self, answer: SegmentedAnswer) -> bool:
        return all(
            item.kind is AnswerSegmentKind.FACTUAL
            or (
                item.template_id is not None
                and self._templates.exact_text(item.template_id) == item.text
            )
            for item in answer.segments
        )

    def _failed(
        self,
        request: GroundingAssuranceRequest,
        snapshot_digest: str,
        failures: tuple[str, ...],
    ) -> GroundingAssuranceResult:
        return self._result(
            request,
            snapshot_digest,
            supported=False,
            unsupported=tuple(item.claim_id for item in request.answer.factual_claims),
            failures=failures,
        )

    def _result(
        self,
        request: GroundingAssuranceRequest,
        snapshot_digest: str,
        *,
        supported: bool,
        unsupported: tuple[str, ...],
        failures: tuple[str, ...],
    ) -> GroundingAssuranceResult:
        return GroundingAssuranceResult(
            supported=supported,
            validator_revision=self._engine.revision,
            evidence_snapshot_sha256=snapshot_digest,
            rendered_text_sha256=sha256(request.answer.rendered_text.encode()).hexdigest(),
            unsupported_claim_ids=unsupported,
            failure_codes=failures,
        )
