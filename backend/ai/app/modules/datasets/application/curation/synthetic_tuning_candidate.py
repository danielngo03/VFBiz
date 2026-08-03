from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, TypeGuard, cast

from app.modules.datasets.application.curation.synthetic_text_quality import (
    assess_synthetic_text_quality,
)

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_SECRET = re.compile(r"(?i)(?:api[_-]?key|secret|password|bearer)\s*[:=]\s*\S+")
_PII = re.compile(
    r"(?i)(?:[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b(?:\+?84|0)\d{8,10}\b|\b[A-HJ-NPR-Z0-9]{17}\b)"
)
_PROMPT_INJECTION = re.compile(
    r"(?i)(?:ignore|bỏ qua).{0,30}(?:system|hệ thống|chỉ dẫn|instruction)"
)
_BRAND_FACT = re.compile(
    r"(?i)\b(?:vinfast|v[\s-]?green|vf\s*[3-9]|giá xe|bảo hành|"
    r"quãng đường|pin thuê|khuyến mại|ưu đãi|hotline)\b"
)
_SPLITS = ("train", "validation", "test")
_LINEAGE_FIELDS = {
    "candidate_id",
    "work_item",
    "generation_run_id",
    "generator_identity",
    "generator_source_sha256",
    "pinned_revisions_sha256",
    "family_lock_sha256",
    "seed_set_id",
    "seed_digest",
    "scenario_id",
    "scenario_digest",
    "prompt_component_ids",
    "response_component_ids",
    "composition_digest",
    "source_refs",
    "golden_or_heldout_seed_refs",
    "record_content_sha256",
}
_RECORD_FIELDS = {
    "family_id",
    "human_adjudicated",
    "labels",
    "lineage",
    "messages",
    "production_eligible",
    "provider_call_made",
    "record_id",
    "release_eligible",
    "response_constraints",
    "source",
    "split",
    "training_eligible",
    "upload_made",
}


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: object) -> str:
    return sha256(canonical_json(value).encode()).hexdigest()


def normalize_text(value: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", value.casefold(), flags=re.UNICODE).split())


def count_words(value: str) -> int:
    return len(_WORD.findall(value))


@dataclass(frozen=True, slots=True)
class CandidateVerification:
    candidate_id: str
    record_count: int
    split_counts: Mapping[str, int]
    unique_composition_ratio: Mapping[str, float]
    maximum_response_share: Mapping[str, float]
    errors: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return not self.errors

    @property
    def report(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "candidate_id": self.candidate_id,
            "errors": list(self.errors),
            "maximum_response_share": dict(self.maximum_response_share),
            "record_count": self.record_count,
            "split_counts": dict(self.split_counts),
            "unique_composition_ratio": dict(self.unique_composition_ratio),
            "verifier_revision": "synthetic-tuning-candidate-v2",
        }


@dataclass(frozen=True, slots=True)
class TrustedCandidateAuthority:
    """Repository-controlled authority that a candidate cannot self-issue."""

    candidate_id: str
    work_item: str
    source: str
    verifier_revision: str
    verifier_source_path: str
    verifier_source_sha256: str
    text_quality_source_path: str
    text_quality_source_sha256: str
    store_source_path: str
    store_source_sha256: str
    voice_rubric_source_path: str
    voice_rubric_file_sha256: str
    voice_rubric_semantic_sha256: str
    domain_pack_source_path: str
    domain_pack_file_sha256: str
    domain_pack_semantic_sha256: str
    generator_identity: str
    generator_source_path: str
    generator_source_sha256: str
    seed_set_id: str
    pinned_revisions_sha256: str
    family_lock_sha256: str
    scenario_lock_sha256: str
    behavior_labels_sha256: str
    governance_metadata_sha256: str
    regression_source_bindings: tuple[tuple[str, str, int], ...]
    allowed_exports: tuple[str, ...]
    expected_record_count: int
    expected_split_counts: Mapping[str, int]

    @property
    def authority_digest(self) -> str:
        return digest(
            {
                "allowed_exports": list(self.allowed_exports),
                "behavior_labels_sha256": self.behavior_labels_sha256,
                "candidate_id": self.candidate_id,
                "expected_record_count": self.expected_record_count,
                "expected_split_counts": dict(self.expected_split_counts),
                "family_lock_sha256": self.family_lock_sha256,
                "domain_pack_file_sha256": self.domain_pack_file_sha256,
                "domain_pack_semantic_sha256": self.domain_pack_semantic_sha256,
                "domain_pack_source_path": self.domain_pack_source_path,
                "generator_identity": self.generator_identity,
                "generator_source_path": self.generator_source_path,
                "generator_source_sha256": self.generator_source_sha256,
                "governance_metadata_sha256": self.governance_metadata_sha256,
                "pinned_revisions_sha256": self.pinned_revisions_sha256,
                "regression_source_bindings": [
                    {
                        "record_id": record_id,
                        "record_sha256": record_sha256,
                        "word_count": word_count,
                    }
                    for record_id, record_sha256, word_count in self.regression_source_bindings
                ],
                "scenario_lock_sha256": self.scenario_lock_sha256,
                "seed_set_id": self.seed_set_id,
                "source": self.source,
                "store_source_path": self.store_source_path,
                "store_source_sha256": self.store_source_sha256,
                "text_quality_source_path": self.text_quality_source_path,
                "text_quality_source_sha256": self.text_quality_source_sha256,
                "verifier_revision": self.verifier_revision,
                "verifier_source_path": self.verifier_source_path,
                "verifier_source_sha256": self.verifier_source_sha256,
                "voice_rubric_file_sha256": self.voice_rubric_file_sha256,
                "voice_rubric_semantic_sha256": self.voice_rubric_semantic_sha256,
                "voice_rubric_source_path": self.voice_rubric_source_path,
                "work_item": self.work_item,
            }
        )


def verify_candidate(
    *,
    records: Sequence[dict[str, Any]],
    family_lock: dict[str, Any],
    pinned: dict[str, Any],
    authority: TrustedCandidateAuthority,
) -> CandidateVerification:
    errors: list[str] = []
    candidate_id = str(pinned.get("candidate_id", ""))
    pinned_digest = digest(pinned)
    lock_digest = digest(family_lock)
    scenario_lock_digest = digest(_scenario_lock_projection(family_lock))
    families_value = family_lock.get("families")
    families = cast(list[object], families_value) if isinstance(families_value, list) else []
    family_by_id: dict[str, dict[str, Any]] = {}
    scenarios_by_family: dict[str, dict[str, dict[str, Any]]] = {}
    for raw_family in families:
        if isinstance(raw_family, dict):
            family = cast(dict[str, Any], raw_family)
            family_id = str(family.get("family_id", ""))
            family_by_id[family_id] = family
            scenarios_by_family[family_id] = _family_scenarios(family)
    if not candidate_id or not family_by_id:
        errors.append("candidate authority is incomplete")
    behavior_labels_value = pinned.get("behavior_labels")
    behavior_labels = (
        cast(dict[str, Any], behavior_labels_value)
        if isinstance(behavior_labels_value, dict)
        else {}
    )
    if (
        family_lock.get("candidate_id") != candidate_id
        or candidate_id != authority.candidate_id
        or pinned.get("verifier_revision") != authority.verifier_revision
        or authority.verifier_revision != "synthetic-tuning-candidate-v2"
        or pinned.get("source") != authority.source
        or pinned.get("work_item") != authority.work_item
        or pinned.get("seed_set_id") != authority.seed_set_id
        or pinned.get("generator_identity") != authority.generator_identity
        or pinned.get("generator_source_sha256") != authority.generator_source_sha256
        or tuple(pinned.get("exports", ())) != authority.allowed_exports
        or pinned.get("voice_rubric_sha256") != authority.voice_rubric_semantic_sha256
        or pinned.get("domain_pack_sha256") != authority.domain_pack_semantic_sha256
        or pinned_digest != authority.pinned_revisions_sha256
        or lock_digest != authority.family_lock_sha256
        or scenario_lock_digest != authority.scenario_lock_sha256
        or digest(behavior_labels) != authority.behavior_labels_sha256
        or not behavior_labels
    ):
        errors.append("candidate authority metadata is incomplete")

    ids: set[str] = set()
    family_splits: dict[str, set[str]] = defaultdict(set)
    split_components: dict[str, set[str]] = defaultdict(set)
    split_messages: dict[str, set[str]] = defaultdict(set)
    split_semantics: dict[str, set[str]] = defaultdict(set)
    split_text_tokens: dict[str, list[tuple[str, frozenset[str]]]] = defaultdict(list)
    response_counts: dict[str, Counter[str]] = defaultdict(Counter)
    composition_counts: dict[str, Counter[str]] = defaultdict(Counter)
    structural_counts: dict[str, Counter[str]] = defaultdict(Counter)
    split_counts: Counter[str] = Counter()

    for record in records:
        record_id = str(record.get("record_id", ""))
        split = str(record.get("split", ""))
        family_id = str(record.get("family_id", ""))
        if set(record) != _RECORD_FIELDS:
            errors.append(f"invalid record fields:{record_id}")
        if record.get("source") != authority.source:
            errors.append(f"source authority mismatch:{record_id}")
        if record_id in ids or not record_id:
            errors.append(f"duplicate or missing record_id:{record_id}")
        ids.add(record_id)
        if split not in _SPLITS:
            errors.append(f"unknown split:{record_id}")
            continue
        split_counts[split] += 1
        family_splits[family_id].add(split)
        locked = family_by_id.get(family_id)
        if not locked or locked.get("split") != split:
            errors.append(f"family lock mismatch:{record_id}")
        elif not _SHA256.fullmatch(str(locked.get("semantic_fingerprint", ""))):
            errors.append(f"invalid family semantic fingerprint:{family_id}")
        else:
            split_semantics[split].add(str(locked["semantic_fingerprint"]))
            behavior = str(locked.get("behavior", ""))
            expected_labels = behavior_labels.get(behavior)
            if (
                not scenarios_by_family.get(family_id)
                or not isinstance(expected_labels, dict)
                or record.get("labels") != expected_labels
            ):
                errors.append(f"label or family authority mismatch:{record_id}")

        for flag in (
            "human_adjudicated",
            "training_eligible",
            "release_eligible",
            "production_eligible",
            "provider_call_made",
            "upload_made",
        ):
            if record.get(flag) is not False:
                errors.append(f"eligibility flag must be false:{record_id}:{flag}")

        messages_value = record.get("messages")
        if not isinstance(messages_value, list):
            errors.append(f"invalid messages:{record_id}")
            continue
        messages = cast(list[object], messages_value)
        if len(messages) != 2:
            errors.append(f"invalid messages:{record_id}")
            continue
        user = _message_content(messages, 0, "user", record_id, errors)
        assistant = _message_content(messages, 1, "assistant", record_id, errors)
        for text in (user, assistant):
            if _PII.search(text):
                errors.append(f"pii candidate:{record_id}")
            if _SECRET.search(text):
                errors.append(f"secret candidate:{record_id}")
            if _PROMPT_INJECTION.search(text):
                errors.append(f"prompt injection candidate:{record_id}")
            if _BRAND_FACT.search(text):
                errors.append(f"unsupported brand fact:{record_id}")
        response_fingerprint = digest(normalize_text(assistant))
        response_counts[split][response_fingerprint] += 1
        split_messages[split].update({digest(normalize_text(user)), response_fingerprint})
        split_text_tokens[split].append(
            (
                record_id,
                frozenset(normalize_text(f"{user} {assistant}").split()),
            )
        )

        lineage_value = record.get("lineage")
        if not isinstance(lineage_value, dict):
            errors.append(f"invalid lineage fields:{record_id}")
            continue
        lineage = cast(dict[str, Any], lineage_value)
        scenario = scenarios_by_family.get(family_id, {}).get(str(lineage.get("scenario_id", "")))
        if set(lineage) != _LINEAGE_FIELDS:
            errors.append(f"invalid lineage fields:{record_id}")
            continue
        if (
            lineage.get("candidate_id") != authority.candidate_id
            or lineage.get("work_item") != authority.work_item
            or lineage.get("generator_identity") != authority.generator_identity
            or lineage.get("generator_source_sha256") != authority.generator_source_sha256
            or lineage.get("pinned_revisions_sha256") != pinned_digest
            or lineage.get("family_lock_sha256") != lock_digest
            or lineage.get("seed_set_id") != authority.seed_set_id
            or locked is None
            or scenario is None
            or lineage.get("scenario_digest") != scenario.get("scenario_digest")
            or lineage.get("scenario_digest")
            != digest(
                {
                    "assistant": assistant,
                    "scenario_id": lineage.get("scenario_id"),
                    "user": user,
                }
            )
            or lineage.get("seed_digest") != scenario.get("seed_digest")
        ):
            errors.append(f"lineage authority mismatch:{record_id}")
        for field in (
            "generator_source_sha256",
            "seed_digest",
            "scenario_digest",
            "composition_digest",
            "record_content_sha256",
        ):
            if not _SHA256.fullmatch(str(lineage.get(field, ""))):
                errors.append(f"invalid lineage digest:{record_id}:{field}")
        if lineage.get("source_refs") != [] or lineage.get("golden_or_heldout_seed_refs") != []:
            errors.append(f"forbidden source or heldout seed reference:{record_id}")
        prompt_components = lineage.get("prompt_component_ids")
        response_components = lineage.get("response_component_ids")
        if not _component_ids(prompt_components) or not _component_ids(response_components):
            errors.append(f"invalid component ids:{record_id}")
        else:
            split_components[split].update(prompt_components)
            split_components[split].update(response_components)
            structural = sorted(
                component
                for component in response_components
                if not component.startswith("response-modifier:")
            )
            structural_kinds = {component.split(":", maxsplit=1)[0] for component in structural}
            if (
                structural_kinds
                != {
                    "response-prefix",
                    "response-bridge",
                    "response-tail",
                }
                or len(structural) != 3
            ):
                errors.append(f"invalid structural components:{record_id}")
            else:
                structural_counts[split][digest(structural)] += 1
        expected_composition = digest(
            {
                "messages": messages,
                "prompt_component_ids": prompt_components,
                "response_component_ids": response_components,
            }
        )
        if lineage.get("composition_digest") != expected_composition:
            errors.append(f"composition digest mismatch:{record_id}")
        composition_counts[split][expected_composition] += 1
        projection = json.loads(canonical_json(record))
        projection["lineage"].pop("record_content_sha256", None)
        if lineage.get("record_content_sha256") != digest(projection):
            errors.append(f"record digest mismatch:{record_id}")

        constraints = record.get("response_constraints")
        _verify_constraints(record_id, assistant, constraints, errors)

    for family_id, observed in family_splits.items():
        if len(observed) != 1:
            errors.append(f"family split leakage:{family_id}")
    for index, left in enumerate(_SPLITS):
        for right in _SPLITS[index + 1 :]:
            if split_components[left] & split_components[right]:
                errors.append(f"component split leakage:{left}:{right}")
            if split_messages[left] & split_messages[right]:
                errors.append(f"message split leakage:{left}:{right}")
            if split_semantics[left] & split_semantics[right]:
                errors.append(f"semantic split leakage:{left}:{right}")
            for left_id, left_tokens in split_text_tokens[left]:
                for right_id, right_tokens in split_text_tokens[right]:
                    union = left_tokens | right_tokens
                    similarity = len(left_tokens & right_tokens) / len(union) if union else 1.0
                    if similarity >= 0.7:
                        errors.append(f"near-duplicate split leakage:{left_id}:{right_id}")

    unique_ratios: dict[str, float] = {}
    maximum_shares: dict[str, float] = {}
    for split in _SPLITS:
        count = split_counts[split]
        unique_ratios[split] = len(composition_counts[split]) / count if count else 0.0
        maximum_shares[split] = (
            max(response_counts[split].values(), default=0) / count if count else 1.0
        )
        if unique_ratios[split] < 0.95:
            errors.append(f"composition diversity below threshold:{split}")
        if maximum_shares[split] > 0.01:
            errors.append(f"response concentration above threshold:{split}")
        structural_share = (
            max(structural_counts[split].values(), default=0) / count if count else 1.0
        )
        if structural_share > 0.01:
            errors.append(f"structural template concentration above threshold:{split}")
    if len(records) < 600:
        errors.append("candidate contains fewer than 600 records")
    if len(records) != authority.expected_record_count:
        errors.append("candidate record count differs from trusted authority")
    if dict(split_counts) != dict(authority.expected_split_counts):
        errors.append("candidate split counts differ from trusted authority")
    if "gemini/test.jsonl" in authority.allowed_exports:
        errors.append("heldout test export is forbidden")
    try:
        text_quality = assess_synthetic_text_quality(records)
        errors.extend(text_quality.errors)
    except ValueError as error:
        errors.append(
            "text-quality-input-invalid:"
            f"{sha256(str(error).encode('utf-8')).hexdigest()[:16]}"
        )

    return CandidateVerification(
        candidate_id=candidate_id,
        record_count=len(records),
        split_counts=dict(split_counts),
        unique_composition_ratio=unique_ratios,
        maximum_response_share=maximum_shares,
        errors=tuple(sorted(set(errors))),
    )


def safety_findings(value: str) -> tuple[str, ...]:
    findings: list[str] = []
    for label, pattern in (
        ("pii", _PII),
        ("secret", _SECRET),
        ("prompt-injection", _PROMPT_INJECTION),
        ("unsupported-brand-fact", _BRAND_FACT),
    ):
        if pattern.search(value):
            findings.append(label)
    if re.search(r"(?i)\{\s*[\"']?(?:tool|function|functionCall)[\"']?\s*:", value):
        findings.append("ad-hoc-tool-call")
    return tuple(findings)


def scenario_lock_digest(family_lock: Mapping[str, object]) -> str:
    return digest(_scenario_lock_projection(family_lock))


def _scenario_lock_projection(family_lock: Mapping[str, object]) -> dict[str, object]:
    families_value = family_lock.get("families")
    families = cast(list[object], families_value) if isinstance(families_value, list) else []
    projection: list[dict[str, object]] = []
    for raw_family in families:
        if not isinstance(raw_family, dict):
            continue
        family = cast(dict[str, Any], raw_family)
        scenarios = _family_scenarios(family)
        projection.append(
            {
                "behavior": family.get("behavior"),
                "family_id": family.get("family_id"),
                "scenarios": [scenarios[key] for key in sorted(scenarios)],
                "semantic_fingerprint": family.get("semantic_fingerprint"),
                "split": family.get("split"),
            }
        )
    return {"candidate_id": family_lock.get("candidate_id"), "families": projection}


def _family_scenarios(family: Mapping[str, object]) -> dict[str, dict[str, Any]]:
    scenarios_value = family.get("scenarios")
    scenarios: list[object]
    if isinstance(scenarios_value, list):
        scenarios = cast(list[object], scenarios_value)
    else:
        scenarios = [
            {
                "scenario_digest": family.get("scenario_digest"),
                "scenario_id": family.get("scenario_id"),
                "seed_digest": family.get("seed_digest"),
            }
        ]
    result: dict[str, dict[str, Any]] = {}
    for value in scenarios:
        if not isinstance(value, dict):
            continue
        scenario = cast(dict[str, Any], value)
        scenario_id = str(scenario.get("scenario_id", ""))
        if (
            not scenario_id
            or not _SHA256.fullmatch(str(scenario.get("scenario_digest", "")))
            or not _SHA256.fullmatch(str(scenario.get("seed_digest", "")))
        ):
            continue
        result[scenario_id] = {
            "scenario_digest": scenario["scenario_digest"],
            "scenario_id": scenario_id,
            "seed_digest": scenario["seed_digest"],
        }
    return result


def _verify_constraints(
    record_id: str,
    assistant: str,
    constraints: object,
    errors: list[str],
) -> None:
    if not isinstance(constraints, dict):
        errors.append(f"missing response constraints:{record_id}")
        return
    constraint_values = cast(dict[str, Any], constraints)
    max_words = constraint_values.get("max_words")
    if isinstance(max_words, int) and count_words(assistant) > max_words:
        errors.append(f"max words exceeded:{record_id}")
    max_questions = constraint_values.get("max_questions")
    if isinstance(max_questions, int) and assistant.count("?") > max_questions:
        errors.append(f"max questions exceeded:{record_id}")
    required_value = constraint_values.get("required_phrases", [])
    required = cast(list[object], required_value) if isinstance(required_value, list) else []
    if not isinstance(required_value, list) or any(
        not isinstance(phrase, str) or phrase not in assistant for phrase in required
    ):
        errors.append(f"required phrase missing:{record_id}")
    forbidden_value = constraint_values.get("forbidden_phrases", [])
    forbidden = cast(list[object], forbidden_value) if isinstance(forbidden_value, list) else []
    if not isinstance(forbidden_value, list) or any(
        isinstance(phrase, str) and phrase in assistant for phrase in forbidden
    ):
        errors.append(f"forbidden phrase present:{record_id}")


def _message_content(
    messages: list[object],
    index: int,
    role: str,
    record_id: str,
    errors: list[str],
) -> str:
    item = messages[index]
    if not isinstance(item, dict):
        errors.append(f"invalid message role:{record_id}:{role}")
        return ""
    message = cast(dict[str, Any], item)
    if message.get("role") != role:
        errors.append(f"invalid message role:{record_id}:{role}")
        return ""
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        errors.append(f"invalid message content:{record_id}:{role}")
        return ""
    return content


def _component_ids(value: object) -> TypeGuard[list[str]]:
    if not isinstance(value, list):
        return False
    items = cast(list[object], value)
    return (
        bool(items)
        and all(isinstance(item, str) and 1 <= len(item) <= 160 for item in items)
        and len(items) == len(set(items))
    )
