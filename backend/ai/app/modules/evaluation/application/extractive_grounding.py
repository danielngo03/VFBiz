import json
import re
import unicodedata
from hashlib import sha256

from app.modules.inference.application import (
    ClaimSupportDecision,
    GenerationRequest,
    GenerationResult,
    normalized_evidence_digest,
)

_TOKEN = re.compile(r"[^\W_]+", flags=re.UNICODE)
_NUMBER = re.compile(r"(?<!\w)[+-]?\d+(?:[.,]\d+)*(?!\w)")
_NEGATION = frozenset({"không", "chưa", "never", "not", "no"})


class DeterministicExtractiveGroundingValidator:
    """Conservative staging baseline for customer factual answers.

    This validator intentionally accepts only extractive statements. It uses
    independent citation membership, lexical containment, numeric consistency
    and negation consistency checks. Paraphrases fail closed until an approved,
    calibrated entailment ensemble is released.
    """

    revision = "deterministic-extractive-v1"

    @property
    def artifact_sha256(self) -> str:
        payload = {
            "revision": self.revision,
            "signals": [
                "citation-membership",
                "lexical-containment",
                "numeric-consistency",
                "negation-consistency",
            ],
            "mode": "all-signals-required",
        }
        canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return sha256(canonical.encode()).hexdigest()

    async def validate(
        self,
        request: GenerationRequest,
        result: GenerationResult,
    ) -> ClaimSupportDecision:
        evidence_by_id = {item.evidence_id: item for item in request.evidence}
        cited = tuple(
            evidence_by_id[item.evidence_id]
            for item in result.citations
            if item.evidence_id in evidence_by_id
        )
        supported = bool(cited) and len(cited) == len(result.citations)
        answer = _normalized(result.answer or "")
        excerpts = tuple(_normalized(item.excerpt) for item in cited)
        if supported:
            supported = bool(answer) and any(answer in excerpt for excerpt in excerpts)
        if supported:
            evidence_numbers = {
                number for excerpt in excerpts for number in _NUMBER.findall(excerpt)
            }
            supported = set(_NUMBER.findall(answer)).issubset(evidence_numbers)
        if supported:
            answer_negation = _tokens(answer) & _NEGATION
            supported = all(
                answer_negation.issubset(_tokens(excerpt)) for excerpt in excerpts
            )
        return ClaimSupportDecision(
            supported=supported,
            validator_revision=self.revision,
            evidence_digest=normalized_evidence_digest(request),
        )


def _normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def _tokens(value: str) -> frozenset[str]:
    return frozenset(match.group(0) for match in _TOKEN.finditer(value))
