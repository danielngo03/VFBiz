"""Dataset quality policy orchestration."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass

from app.modules.datasets.domain import CanonicalDatasetRecord, RegistryInvariantError

_TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class ContaminationIndex:
    exact_hashes: frozenset[str]
    split_family_ids: frozenset[str]
    minhash_signatures: frozenset[tuple[int, ...]]
    permutations: int = 32
    similarity_threshold: float = 0.60

    @classmethod
    def from_held_out(
        cls,
        records: tuple[CanonicalDatasetRecord, ...],
        *,
        permutations: int = 32,
        similarity_threshold: float = 0.60,
    ) -> ContaminationIndex:
        if not 0 < similarity_threshold <= 1:
            raise RegistryInvariantError("similarity threshold must be in (0, 1]")
        return cls(
            exact_hashes=frozenset(_record_text_hash(record) for record in records),
            split_family_ids=frozenset(record.classification.split_family_id for record in records),
            minhash_signatures=frozenset(
                minhash_signature(_record_text(record), permutations=permutations)
                for record in records
            ),
            permutations=permutations,
            similarity_threshold=similarity_threshold,
        )

    def reject_if_contaminated(self, record: CanonicalDatasetRecord) -> None:
        if record.classification.split_family_id in self.split_family_ids:
            raise RegistryInvariantError("candidate shares a held-out split family")
        if _record_text_hash(record) in self.exact_hashes:
            raise RegistryInvariantError("candidate exactly matches held-out content")
        candidate = minhash_signature(_record_text(record), permutations=self.permutations)
        if any(
            signature_similarity(candidate, held_out) >= self.similarity_threshold
            for held_out in self.minhash_signatures
        ):
            raise RegistryInvariantError("candidate near-duplicates held-out content")


class ExactDeduplicator:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    def accept(self, record: CanonicalDatasetRecord) -> bool:
        digest = _record_text_hash(record)
        if digest in self._seen:
            return False
        self._seen.add(digest)
        return True


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    normalized = normalized.replace("\u00a0", " ")
    return " ".join(normalized.split()).strip()


def minhash_signature(value: str, *, permutations: int = 32) -> tuple[int, ...]:
    if permutations < 8:
        raise RegistryInvariantError("MinHash requires at least eight permutations")
    tokens = _TOKEN_PATTERN.findall(normalize_text(value).casefold())
    shingles = {
        " ".join(tokens[index : index + 3]) for index in range(max(1, len(tokens) - 2))
    } or {""}
    signature: list[int] = []
    for seed in range(permutations):
        signature.append(
            min(
                int.from_bytes(
                    hashlib.sha256(f"{seed}:{shingle}".encode()).digest()[:8],
                    "big",
                )
                for shingle in shingles
            )
        )
    return tuple(signature)


def signature_similarity(first: tuple[int, ...], second: tuple[int, ...]) -> float:
    if not first or len(first) != len(second):
        raise RegistryInvariantError("MinHash signatures must have equal non-zero length")
    return sum(left == right for left, right in zip(first, second, strict=True)) / len(first)


def _record_text_hash(record: CanonicalDatasetRecord) -> str:
    return hashlib.sha256(normalize_text(_record_text(record)).casefold().encode()).hexdigest()


def _record_text(record: CanonicalDatasetRecord) -> str:
    return json.dumps(
        record.payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
