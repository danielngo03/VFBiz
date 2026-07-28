from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID, uuid5

from app.modules.datasets.domain.registry import RegistryInvariantError


class GoldenSuite(StrEnum):
    FACTUAL_CITATION = "factual-citation"
    RETRIEVAL_NO_EVIDENCE = "retrieval-no-evidence"
    INTENT_OOD = "intent-ood-clarification"
    MULTI_TURN_CONTEXT = "multi-turn-context"
    SAFETY_PRIVACY = "safety-legal-privacy"
    TOOL_AUTHORIZATION = "tool-authorization"
    STATE_RESILIENCE = "state-resilience"
    HANDOFF = "handoff"
    VIETNAMESE_ROBUSTNESS = "vietnamese-robustness"


class GoldenState(StrEnum):
    CANDIDATE = "candidate"
    ANNOTATED = "annotated"
    REVIEWED = "reviewed"
    ADJUDICATED = "adjudicated"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class GoldenCase:
    case_id: UUID
    suite: GoldenSuite
    split_family_id: str
    contamination_fingerprint: str
    state: GoldenState = GoldenState.CANDIDATE
    author_ref: str | None = None
    reviewer_ref: str | None = None
    adjudicator_ref: str | None = None
    annotation_sha256: str | None = None
    review_sha256: str | None = None
    adjudication_sha256: str | None = None
    row_version: int = 1

    def __post_init__(self) -> None:
        if not self.split_family_id.strip():
            raise RegistryInvariantError("Golden split family is required")
        _digest(self.contamination_fingerprint)
        if self.row_version < 1:
            raise RegistryInvariantError("Golden row version must be positive")
        self.validate_release_evidence()

    @property
    def allowed_use(self) -> str:
        return "evaluation"

    def validate_release_evidence(self) -> None:
        if self.state in {GoldenState.ANNOTATED, GoldenState.REVIEWED, GoldenState.ADJUDICATED}:
            if not self.author_ref or not self.annotation_sha256:
                raise RegistryInvariantError("annotated Golden case requires author evidence")
            _actor(self.author_ref)
            _digest(self.annotation_sha256)
        if self.state in {GoldenState.REVIEWED, GoldenState.ADJUDICATED}:
            if not self.reviewer_ref or not self.review_sha256:
                raise RegistryInvariantError("reviewed Golden case requires reviewer evidence")
            if self.reviewer_ref == self.author_ref:
                raise RegistryInvariantError("Golden reviewer must be independent")
            _digest(self.review_sha256)
        if self.state is GoldenState.ADJUDICATED:
            if not self.adjudicator_ref or not self.adjudication_sha256:
                raise RegistryInvariantError("adjudicated Golden case requires decision evidence")
            if self.adjudicator_ref in {self.author_ref, self.reviewer_ref}:
                raise RegistryInvariantError("Golden adjudicator must be independent")
            _digest(self.adjudication_sha256)

    def annotate(self, *, actor_ref: str, evidence_sha256: str) -> GoldenCase:
        if self.state is not GoldenState.CANDIDATE:
            raise RegistryInvariantError("only a candidate can be annotated")
        return replace(
            self,
            state=GoldenState.ANNOTATED,
            author_ref=_actor(actor_ref),
            annotation_sha256=_digest(evidence_sha256),
            row_version=self.row_version + 1,
        )

    def review(self, *, actor_ref: str, evidence_sha256: str) -> GoldenCase:
        actor = _actor(actor_ref)
        if self.state is not GoldenState.ANNOTATED:
            raise RegistryInvariantError("only an annotated case can be reviewed")
        if actor == self.author_ref:
            raise RegistryInvariantError("case author cannot review their own case")
        return replace(
            self,
            state=GoldenState.REVIEWED,
            reviewer_ref=actor,
            review_sha256=_digest(evidence_sha256),
            row_version=self.row_version + 1,
        )

    def adjudicate(self, *, actor_ref: str, evidence_sha256: str) -> GoldenCase:
        actor = _actor(actor_ref)
        if self.state is not GoldenState.REVIEWED:
            raise RegistryInvariantError("only an independently reviewed case can be adjudicated")
        if actor in {self.author_ref, self.reviewer_ref}:
            raise RegistryInvariantError("adjudicator must be independent")
        return replace(
            self,
            state=GoldenState.ADJUDICATED,
            adjudicator_ref=actor,
            adjudication_sha256=_digest(evidence_sha256),
            row_version=self.row_version + 1,
        )


_SMOKE_ALLOCATION: dict[GoldenSuite, int] = {
    GoldenSuite.FACTUAL_CITATION: 25,
    GoldenSuite.RETRIEVAL_NO_EVIDENCE: 15,
    GoldenSuite.INTENT_OOD: 12,
    GoldenSuite.MULTI_TURN_CONTEXT: 12,
    GoldenSuite.SAFETY_PRIVACY: 12,
    GoldenSuite.TOOL_AUTHORIZATION: 10,
    GoldenSuite.STATE_RESILIENCE: 8,
    GoldenSuite.HANDOFF: 3,
    GoldenSuite.VIETNAMESE_ROBUSTNESS: 3,
}


def build_smoke_candidates(*, namespace: UUID, seed_revision: str) -> tuple[GoldenCase, ...]:
    if not seed_revision.strip():
        raise RegistryInvariantError("smoke pack seed revision is required")
    cases: list[GoldenCase] = []
    for suite, count in _SMOKE_ALLOCATION.items():
        for index in range(count):
            family = f"smoke:{seed_revision}:{suite.value}:{index:03d}"
            cases.append(
                GoldenCase(
                    case_id=uuid5(namespace, family),
                    suite=suite,
                    split_family_id=family,
                    contamination_fingerprint=_content_fingerprint(
                        seed_revision=seed_revision,
                        suite=suite,
                        family=family,
                    ),
                )
            )
    return tuple(cases)


def select_releasable_cases(cases: tuple[GoldenCase, ...]) -> tuple[GoldenCase, ...]:
    if not cases:
        raise RegistryInvariantError("Golden release cannot be empty")
    families = [case.split_family_id for case in cases]
    fingerprints = [case.contamination_fingerprint for case in cases]
    if len(families) != len(set(families)) or len(fingerprints) != len(set(fingerprints)):
        raise RegistryInvariantError("Golden release contains split-family contamination")
    if any(case.state is not GoldenState.ADJUDICATED for case in cases):
        raise RegistryInvariantError("Golden release requires adjudicated cases only")
    for case in cases:
        case.validate_release_evidence()
    return tuple(sorted(cases, key=lambda case: (case.suite.value, case.split_family_id)))


def _actor(value: str) -> str:
    if not value.strip():
        raise RegistryInvariantError("human actor reference is required")
    return value


def _digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise RegistryInvariantError("evidence and contamination digests use SHA-256 hex")
    return value


def _content_fingerprint(*, seed_revision: str, suite: GoldenSuite, family: str) -> str:
    payload = f"{seed_revision}\n{suite.value}\n{family}".encode()
    return hashlib.sha256(payload).hexdigest()
