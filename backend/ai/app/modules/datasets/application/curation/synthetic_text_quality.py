"""Deterministic text-derived quality gates for synthetic behavior datasets.

Candidate-issued component identifiers are lineage, not evidence of linguistic
diversity.  This module intentionally derives every metric from the rendered
messages so unique record IDs cannot make a templated dataset look diverse.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from hashlib import sha256
from itertools import combinations
from typing import Any, cast

_WHITESPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"[0-9A-Za-zÀ-ỹĐđ]+", re.UNICODE)
_ALLOWED_SPLITS = frozenset({"train", "validation", "test"})
_DEFAULT_IMPLEMENTATION_TERMS = frozenset(
    {
        "fallback",
        "lineage",
        "pipeline",
        "prompt",
        "runtime",
        "token",
        "workflow",
    }
)


@dataclass(frozen=True, slots=True)
class SyntheticTextQualityPolicy:
    prefix_words: int = 5
    maximum_prefix_share: float = 0.02
    cross_split_similarity_threshold: float = 0.90
    maximum_cross_split_near_duplicates: int = 0
    maximum_reported_pairs: int = 20
    forbidden_implementation_terms: frozenset[str] = _DEFAULT_IMPLEMENTATION_TERMS

    def __post_init__(self) -> None:
        if self.prefix_words < 1:
            raise ValueError("prefix_words must be positive")
        if not 0 < self.maximum_prefix_share <= 1:
            raise ValueError("maximum_prefix_share must be in (0, 1]")
        if not 0 < self.cross_split_similarity_threshold <= 1:
            raise ValueError("cross_split_similarity_threshold must be in (0, 1]")
        if self.maximum_cross_split_near_duplicates < 0:
            raise ValueError("maximum_cross_split_near_duplicates cannot be negative")
        if self.maximum_reported_pairs < 1:
            raise ValueError("maximum_reported_pairs must be positive")


@dataclass(frozen=True, slots=True)
class SyntheticTextQualityAssessment:
    record_count: int
    split_counts: Mapping[str, int]
    maximum_prefix_share: Mapping[str, float]
    cross_split_near_duplicate_count: int
    implementation_term_count: int
    errors: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class _RenderedRecord:
    record_id: str
    split: str
    assistant: str
    comparison_assistant: str
    character_counts: Mapping[str, int]
    tokens: tuple[str, ...]


def assess_synthetic_text_quality(
    records: Iterable[Mapping[str, Any]],
    *,
    policy: SyntheticTextQualityPolicy | None = None,
) -> SyntheticTextQualityAssessment:
    """Assess rendered language without trusting candidate component metadata."""

    selected_policy = policy or SyntheticTextQualityPolicy()
    rendered = tuple(_rendered_record(record) for record in records)
    errors: list[str] = []

    split_records: dict[str, list[_RenderedRecord]] = defaultdict(list)
    for record in rendered:
        split_records[record.split].append(record)

    maximum_prefix_share: dict[str, float] = {}
    for split, values in sorted(split_records.items()):
        prefixes = Counter(
            value.tokens[: selected_policy.prefix_words] for value in values
        )
        maximum = max(prefixes.values(), default=0)
        share = maximum / len(values) if values else 0.0
        maximum_prefix_share[split] = share
        for prefix, count in sorted(
            prefixes.items(),
            key=lambda item: (-item[1], item[0]),
        ):
            prefix_share = count / len(values) if values else 0.0
            if prefix_share <= selected_policy.maximum_prefix_share:
                break
            errors.append(
                "text-prefix-concentration:"
                f"{split}:{count}/{len(values)}:{_fingerprint_tokens(prefix)}"
            )

    implementation_term_count = 0
    forbidden_terms = tuple(
        sorted(
            {
                tuple(_TOKEN.findall(_normalize_text(term)))
                for term in selected_policy.forbidden_implementation_terms
            }
        )
    )
    for record in rendered:
        matched = tuple(
            term
            for term in forbidden_terms
            if term and _contains_token_sequence(record.tokens, term)
        )
        if not matched:
            continue
        implementation_term_count += len(matched)
        errors.append(
            "implementation-term:"
            f"{_fingerprint_identifier(record.record_id)}:"
            f"{_fingerprint_tokens(tuple(token for term in matched for token in term))}"
        )

    near_duplicate_pairs: list[tuple[str, str, float]] = []
    for left_split, right_split in combinations(sorted(split_records), 2):
        for left in split_records[left_split]:
            for right in split_records[right_split]:
                if not _could_be_near_duplicate(
                    left,
                    right,
                    similarity_threshold=(
                        selected_policy.cross_split_similarity_threshold
                    ),
                ):
                    continue
                similarity = (
                    1.0
                    if left.comparison_assistant == right.comparison_assistant
                    else SequenceMatcher(
                        None,
                        left.comparison_assistant,
                        right.comparison_assistant,
                        autojunk=False,
                    ).ratio()
                )
                if similarity >= selected_policy.cross_split_similarity_threshold:
                    near_duplicate_pairs.append(
                        (left.record_id, right.record_id, similarity)
                    )

    near_duplicate_pairs.sort(key=lambda item: (-item[2], item[0], item[1]))
    if (
        len(near_duplicate_pairs)
        > selected_policy.maximum_cross_split_near_duplicates
    ):
        errors.append(
            "cross-split-near-duplicate-count:"
            f"{len(near_duplicate_pairs)}"
        )
        errors.extend(
            "cross-split-near-duplicate:"
            f"{_fingerprint_identifier(left)}:"
            f"{_fingerprint_identifier(right)}:{similarity:.3f}"
            for left, right, similarity in near_duplicate_pairs[
                : selected_policy.maximum_reported_pairs
            ]
        )

    return SyntheticTextQualityAssessment(
        record_count=len(rendered),
        split_counts={
            split: len(values) for split, values in sorted(split_records.items())
        },
        maximum_prefix_share=maximum_prefix_share,
        cross_split_near_duplicate_count=len(near_duplicate_pairs),
        implementation_term_count=implementation_term_count,
        errors=tuple(sorted(set(errors))),
    )


def _rendered_record(record: Mapping[str, Any]) -> _RenderedRecord:
    record_id = str(record.get("record_id", "")).strip()
    split = str(record.get("split", "")).strip()
    if not record_id or not split:
        raise ValueError("record_id and split are required")
    safe_record_id = _fingerprint_identifier(record_id)
    if split not in _ALLOWED_SPLITS:
        raise ValueError(f"unsupported split:{_fingerprint_identifier(split)}")
    messages_value = record.get("messages")
    if not isinstance(messages_value, list):
        raise ValueError(f"messages must be a list:{safe_record_id}")
    messages = cast(list[object], messages_value)
    assistant_messages: list[Mapping[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        typed_message = cast(dict[str, Any], message)
        if typed_message.get("role") == "assistant":
            assistant_messages.append(typed_message)
    if len(assistant_messages) != 1:
        raise ValueError(
            f"exactly one assistant message is required:{safe_record_id}"
        )
    assistant = str(assistant_messages[0].get("content", "")).strip()
    if not assistant:
        raise ValueError(f"assistant content is required:{safe_record_id}")
    tokens = tuple(_TOKEN.findall(_normalize_text(assistant)))
    comparison = "".join(tokens)
    return _RenderedRecord(
        record_id=record_id,
        split=split,
        assistant=assistant,
        comparison_assistant=comparison,
        character_counts=Counter(comparison),
        tokens=tokens,
    )


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return _WHITESPACE.sub(" ", normalized).strip()


def _could_be_near_duplicate(
    left: _RenderedRecord,
    right: _RenderedRecord,
    *,
    similarity_threshold: float,
) -> bool:
    longer = max(
        len(left.comparison_assistant),
        len(right.comparison_assistant),
    )
    if longer == 0:
        return True
    total_length = len(left.comparison_assistant) + len(
        right.comparison_assistant
    )
    length_upper_bound = 2 * min(
        len(left.comparison_assistant),
        len(right.comparison_assistant),
    ) / total_length
    if length_upper_bound < similarity_threshold:
        return False
    common_character_count = sum(
        min(count, right.character_counts.get(character, 0))
        for character, count in left.character_counts.items()
    )
    character_upper_bound = 2 * common_character_count / total_length
    return character_upper_bound >= similarity_threshold


def _fingerprint_tokens(tokens: tuple[str, ...]) -> str:
    return sha256(" ".join(tokens).encode("utf-8")).hexdigest()[:16]


def _fingerprint_identifier(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:16]


def _contains_token_sequence(
    tokens: tuple[str, ...],
    sequence: tuple[str, ...],
) -> bool:
    width = len(sequence)
    return any(
        tokens[index : index + width] == sequence
        for index in range(len(tokens) - width + 1)
    )
