"""Final developer rehearsal revision after the bounded review/fix cycle."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from typing import Any

from app.modules.datasets.application.evaluation.golden_rehearsal import (
    RehearsalBundle,
    verify_rehearsal_bundle,
)
from app.modules.datasets.application.evaluation.golden_rehearsal_v2 import (
    build_rehearsal_bundle_v2,
)
from app.modules.datasets.domain import RegistryInvariantError

REHEARSAL_V3_DATASET_ID = "vivi-customer-assistant-golden-grade-rehearsal-v3"
REHEARSAL_V3_GENERATOR_REVISION = "golden-rehearsal-generator-v3"
REHEARSAL_V3_SUITE_REVISION = "vivi-golden-v2-rehearsal-v3"
REHEARSAL_V3_RUBRIC_REVISION = "vivi-text-voice-v1"

_VOICE_DIMENSIONS = [
    "vietnamese-register",
    "response-economy",
    "clarification-recovery",
    "task-transparency",
    "brand-safe-naturalness",
]

_FAMILY_BY_EXACT_VALUE = {
    "42 phút": "synthetic-charge-duration",
    "25 phần trăm": "synthetic-minimum-test-battery",
    "12 phút": "synthetic-software-check-duration",
    "5 mét": "synthetic-cable-length",
    "15 phút": "synthetic-appointment-hold",
    "30 ngày": "synthetic-tire-check-cycle",
    "2 ngôn ngữ": "synthetic-profile-language-count",
    "320 ki-lô-gam": "synthetic-test-compartment-load",
    "1,5 mét": "synthetic-warning-distance",
    "20 phút": "synthetic-session-retention",
    "10 phút": "synthetic-token-expiry",
    "16 trang": "synthetic-guide-page-count",
}


def build_rehearsal_bundle_v3(*, generator_source_sha256: str) -> RehearsalBundle:
    """Build v3 with exact fact-family identity and immutable v3 metadata."""

    generator_source_sha256 = _sha256(generator_source_sha256)
    v2 = build_rehearsal_bundle_v2(generator_source_sha256=generator_source_sha256)
    cases = [deepcopy(case) for case in v2.cases]
    suite_indexes: Counter[str] = Counter()
    for case in cases:
        suite_id = case["suite_id"]
        suite_index = suite_indexes[suite_id]
        suite_indexes[suite_id] += 1
        case["case_id"] = case["case_id"].replace(
            "vivi-rehearsal-v2-",
            "vivi-rehearsal-v3-",
            1,
        )
        case["suite_revision"] = REHEARSAL_V3_SUITE_REVISION
        case["rubric_revision"] = REHEARSAL_V3_RUBRIC_REVISION
        case["lineage"]["seed_refs"] = [
            f"synthetic:{REHEARSAL_V3_GENERATOR_REVISION}"
        ]
        exact_value = _exact_fact_value(case)
        if exact_value in _FAMILY_BY_EXACT_VALUE:
            case["split_family_id"] = (
                f"rehearsal-v3:family:{_FAMILY_BY_EXACT_VALUE[exact_value]}"
            )
        else:
            suffix = case["split_family_id"].split(":", maxsplit=1)[-1]
            case["split_family_id"] = f"rehearsal-v3:{suffix}"
        _normalize_no_evidence_precedence(case, suite_index)

    case_tuple = tuple(cases)
    cases_jsonl = b"".join(_canonical_json(case) + b"\n" for case in case_tuple)
    cases_sha256 = hashlib.sha256(cases_jsonl).hexdigest()
    base_manifest = deepcopy(v2.manifest)
    base_manifest.pop("bundle_digest")
    base_manifest.update(
        {
            "schema_version": 3,
            "dataset_id": REHEARSAL_V3_DATASET_ID,
            "generator_revision": REHEARSAL_V3_GENERATOR_REVISION,
            "generator_source_sha256": generator_source_sha256,
            "generation_run_ref": "run-vfbiz-0135-rehearsal-v3-20260730",
            "suite_revision": REHEARSAL_V3_SUITE_REVISION,
            "rubric_revision": REHEARSAL_V3_RUBRIC_REVISION,
            "case_count": len(case_tuple),
            "family_count": len({case["split_family_id"] for case in case_tuple}),
            "suite_counts": dict(
                sorted(Counter(case["suite_id"] for case in case_tuple).items())
            ),
            "cases_sha256": cases_sha256,
            "ambiguity_precedence": {
                "missing_lookup_identity": "clarification_required",
                "fully_specified_without_approved_evidence": "refusal",
                "tool_request_missing_required_argument": "clarification_required",
                "fully_specified_authorized_tool_request": "tool_proposal",
            },
            "supersedes_rejected_candidates": [
                "vivi-customer-assistant-golden-grade-rehearsal-v1",
                "vivi-customer-assistant-golden-grade-rehearsal-v2",
            ],
        }
    )
    bundle_digest = hashlib.sha256(_canonical_json(base_manifest)).hexdigest()
    manifest = {**base_manifest, "bundle_digest": bundle_digest}
    bundle = RehearsalBundle(
        cases=case_tuple,
        cases_jsonl=cases_jsonl,
        manifest_json=_canonical_json(manifest) + b"\n",
        manifest=manifest,
        bundle_digest=bundle_digest,
    )
    verify_rehearsal_bundle_v3(
        manifest_bytes=bundle.manifest_json,
        cases_bytes=bundle.cases_jsonl,
        expected_digest=bundle.bundle_digest,
    )
    return bundle


def verify_rehearsal_bundle_v3(
    *,
    manifest_bytes: bytes,
    cases_bytes: bytes,
    expected_digest: str,
) -> dict[str, Any]:
    """Require cryptographic and semantic validity for every persisted v3 row."""

    expected_digest = _sha256(expected_digest)
    verified = verify_rehearsal_bundle(
        manifest_bytes=manifest_bytes,
        cases_bytes=cases_bytes,
        expected_digest=expected_digest,
    )
    try:
        manifest = json.loads(manifest_bytes)
        cases = tuple(json.loads(line) for line in cases_bytes.splitlines() if line)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RegistryInvariantError("rehearsal v3 contains invalid JSON") from error

    if (
        manifest.get("schema_version") != 3
        or manifest.get("dataset_id") != REHEARSAL_V3_DATASET_ID
        or manifest.get("suite_revision") != REHEARSAL_V3_SUITE_REVISION
        or manifest.get("rubric_revision") != REHEARSAL_V3_RUBRIC_REVISION
    ):
        raise RegistryInvariantError("rehearsal v3 manifest authority mismatch")
    _sha256(manifest.get("generator_source_sha256", ""))
    if manifest.get("governance", {}).get("human_approval_evidence") != []:
        raise RegistryInvariantError("rehearsal v3 cannot claim human approval")
    if len(cases) != 100 or manifest.get("case_count") != 100:
        raise RegistryInvariantError("rehearsal v3 must contain exactly 100 cases")
    if len({case.get("case_id") for case in cases}) != 100:
        raise RegistryInvariantError("rehearsal v3 case IDs must be unique")
    suite_counts = dict(sorted(Counter(case.get("suite_id") for case in cases).items()))
    if manifest.get("suite_counts") != suite_counts:
        raise RegistryInvariantError("rehearsal v3 suite counts mismatch")
    family_count = len({case.get("split_family_id") for case in cases})
    if manifest.get("family_count") != family_count or family_count != 85:
        raise RegistryInvariantError("rehearsal v3 family allocation mismatch")

    observed_fact_families: dict[str, set[str]] = {
        value: set() for value in _FAMILY_BY_EXACT_VALUE
    }
    for case in cases:
        _verify_case_policy(case)
        value = _exact_fact_value(case)
        if value in _FAMILY_BY_EXACT_VALUE:
            expected_family = (
                f"rehearsal-v3:family:{_FAMILY_BY_EXACT_VALUE[value]}"
            )
            if case["split_family_id"] != expected_family:
                raise RegistryInvariantError("rehearsal v3 semantic family mismatch")
            observed_fact_families[value].add(case["split_family_id"])
    if any(len(families) != 1 for families in observed_fact_families.values()):
        raise RegistryInvariantError("rehearsal v3 semantic family coverage mismatch")
    return verified


def _verify_case_policy(case: dict[str, Any]) -> None:
    review = case.get("review", {})
    lineage = case.get("lineage", {})
    assertions = case.get("initial_context", {}).get("evaluation_assertions", {})
    if (
        case.get("allowed_use") != "evaluation"
        or review
        != {
            "status": "pending",
            "human_label": None,
            "reviewer_role": None,
            "adjudication_evidence": [],
        }
        or lineage
        != {
            "seed_refs": [f"synthetic:{REHEARSAL_V3_GENERATOR_REVISION}"],
            "source_refs": [],
        }
    ):
        raise RegistryInvariantError(
            "rehearsal v3 cases must remain pending, synthetic, and evaluation-only"
        )
    if (
        case.get("suite_revision") != REHEARSAL_V3_SUITE_REVISION
        or case.get("rubric_revision") != REHEARSAL_V3_RUBRIC_REVISION
        or assertions.get("voice_dimensions") != _VOICE_DIMENSIONS
    ):
        raise RegistryInvariantError("rehearsal v3 case authority mismatch")


def _exact_fact_value(case: dict[str, Any]) -> str | None:
    claims = case.get("expected", {}).get("required_claims", [])
    if not claims:
        return None
    text = claims[0].get("text", "")
    if " là " not in text:
        return None
    return text.rsplit(" là ", maxsplit=1)[-1].removesuffix(".")


def _normalize_no_evidence_precedence(
    case: dict[str, Any],
    suite_index: int,
) -> None:
    if case["suite_id"] != "retrieval-no-evidence":
        return
    fully_specified_prompts = {
        0: "Giá bán hôm nay của MẪU_THỬ_NO_SOURCE_01 tại thị trường VN là bao nhiêu?",
        4: (
            "Lịch giao MẪU_THỬ_NO_SOURCE_05 tại điểm LAB-HCM-01 hiện sớm nhất "
            "là khi nào?"
        ),
        5: (
            "Điểm LAB-HCM-02 còn MẪU_THỬ_NO_SOURCE_06 màu xanh trong kho "
            "hôm nay không?"
        ),
        9: (
            "Thời gian sạc của MẪU_THỬ_NO_SOURCE_10, biến thể LAB-V1, "
            "theo chính sách hiện hành là bao lâu?"
        ),
        11: (
            "Giá phụ tùng mã PART-SYNTH-12 cho MẪU_THỬ_NO_SOURCE_12 "
            "tại thị trường VN là bao nhiêu?"
        ),
    }
    if suite_index not in fully_specified_prompts:
        return
    case["conversation"] = [
        {"role": "user", "content": fully_specified_prompts[suite_index]}
    ]
    expected = case["expected"]
    expected["outcome"] = "refusal"
    expected["clarification_slots"] = []
    expected["reason_code"] = "approved_evidence_unavailable"


def _sha256(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise RegistryInvariantError("rehearsal v3 digest must be SHA-256 hex")
    return value


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
