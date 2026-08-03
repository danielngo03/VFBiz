"""Reviewed revision of the synthetic Customer Assistant rehearsal bundle."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from typing import Any

from app.modules.datasets.application.evaluation.golden_rehearsal import (
    RehearsalBundle,
    build_rehearsal_bundle,
    verify_rehearsal_bundle,
)
from app.modules.datasets.domain import RegistryInvariantError

REHEARSAL_V2_DATASET_ID = "vivi-customer-assistant-golden-grade-rehearsal-v2"
REHEARSAL_V2_GENERATOR_REVISION = "golden-rehearsal-generator-v2"
REHEARSAL_V2_SUITE_REVISION = "vivi-golden-v2-rehearsal-v2"
REHEARSAL_V2_RUBRIC_REVISION = "vivi-text-voice-v1"

_AUTHORITY_BINDINGS: dict[str, dict[str, str]] = {
    "suite_candidate": {
        "revision": "customer-assistant-golden-v1-candidate",
        "file_sha256": "ef748537dbebc0ae787c84e859cb1755fca864544501d37c823374058962c2a6",
        "semantic_digest": "b223c5394201ae67c3ce0a88d05da1850ae51018b8e85129b030c60854cdeb5e",
        "status": "human-blocked",
    },
    "voice_rubric": {
        "revision": "vivi-text-voice-v1",
        "file_sha256": "41d85114c6aaac140f351560cd852d072be14ccb5e5612e575b08f7eb8ce3e37",
        "semantic_digest": "548051aab2d5f019693c0a45d94dfc421296300555de5ea1e424a4807c9e9f2d",
        "status": "candidate",
    },
    "voice_domain_pack": {
        "revision": "vivi-text-domain-pack-v1",
        "file_sha256": "fc9d779292c4d75b18af6d7d27dfb8a1f95e32da467e94eec2e29e447d4ad415",
        "semantic_digest": "23b16f3cf148f456c8ffd8c510fa7e44352e56baf7925b17b6b727b856414b57",
        "status": "candidate",
    },
    "voice_board_policy": {
        "revision": "vivi-text-board-policy-v1",
        "file_sha256": "3f98556a6fcbab836d32e42c6081cc0c3235a42ee444075bc75f41ce9f2c33b3",
        "semantic_digest": "d16524120b5613b991672d9d57b36554deb1c4746b2b6f1d42e2b667bb19f3a1",
        "status": "human-blocked",
    },
}

_SHARED_FACT_FAMILIES: tuple[tuple[str, str], ...] = (
    ("42 phút", "synthetic-charge-duration"),
    ("25 phần trăm", "synthetic-minimum-test-battery"),
    ("12 phút", "synthetic-software-check-duration"),
    ("5 mét", "synthetic-cable-length"),
    ("15 phút", "synthetic-appointment-hold"),
    ("30 ngày", "synthetic-tire-check-cycle"),
    ("2 ngôn ngữ", "synthetic-profile-language-count"),
    ("320 ki-lô-gam", "synthetic-test-compartment-load"),
    ("1,5 mét", "synthetic-warning-distance"),
    ("20 phút", "synthetic-session-retention"),
    ("10 phút", "synthetic-token-expiry"),
    ("16 trang", "synthetic-guide-page-count"),
)

_VOICE_DIMENSIONS = (
    "vietnamese-register",
    "response-economy",
    "clarification-recovery",
    "task-transparency",
    "brand-safe-naturalness",
)

_ALLOWED_OUTCOMES = {
    "answer",
    "clarification_required",
    "refusal",
    "handoff_recommended",
    "tool_proposal",
    "cancelled",
    "failed_safely",
}


def build_rehearsal_bundle_v2(*, generator_source_sha256: str) -> RehearsalBundle:
    """Build the v2 candidate with review findings resolved but no approval."""

    generator_source_sha256 = _sha256(generator_source_sha256)
    base = build_rehearsal_bundle()
    cases = [deepcopy(case) for case in base.cases]
    suite_indexes: Counter[str] = Counter()
    for case in cases:
        suite_id = case["suite_id"]
        suite_index = suite_indexes[suite_id]
        suite_indexes[suite_id] += 1
        case["case_id"] = case["case_id"].replace(
            "vivi-rehearsal-",
            "vivi-rehearsal-v2-",
            1,
        )
        case["suite_revision"] = REHEARSAL_V2_SUITE_REVISION
        case["rubric_revision"] = REHEARSAL_V2_RUBRIC_REVISION
        case["lineage"]["seed_refs"] = [
            f"synthetic:{REHEARSAL_V2_GENERATOR_REVISION}"
        ]
        case["split_family_id"] = _family_for(case)
        _add_voice_assertions(case)
        _correct_outcome_precedence(case, suite_index)
        _add_typed_state_assertions(case)

    case_tuple = tuple(cases)
    cases_jsonl = b"".join(_canonical_json(case) + b"\n" for case in case_tuple)
    cases_sha256 = hashlib.sha256(cases_jsonl).hexdigest()
    suite_counts = dict(sorted(Counter(case["suite_id"] for case in case_tuple).items()))
    base_manifest: dict[str, Any] = {
        "schema_version": 2,
        "dataset_id": REHEARSAL_V2_DATASET_ID,
        "dataset_kind": "synthetic-golden-grade-rehearsal",
        "generator_revision": REHEARSAL_V2_GENERATOR_REVISION,
        "generator_source_sha256": generator_source_sha256,
        "generation_run_ref": "run-vfbiz-0135-rehearsal-v2-20260730",
        "suite_revision": REHEARSAL_V2_SUITE_REVISION,
        "rubric_revision": REHEARSAL_V2_RUBRIC_REVISION,
        "authority_bindings": deepcopy(_AUTHORITY_BINDINGS),
        "allowed_use": "evaluation",
        "environment": "development",
        "visibility": "developer-only",
        "golden": False,
        "human_adjudicated": False,
        "training_eligible": False,
        "release_eligible": False,
        "public_serving_eligible": False,
        "provider_calls": 0,
        "source_policy": "synthetic-facts-only-no-production-source",
        "case_count": len(case_tuple),
        "family_count": len({case["split_family_id"] for case in case_tuple}),
        "suite_counts": suite_counts,
        "cases_file": "cases.jsonl",
        "cases_sha256": cases_sha256,
        "governance": {
            "owner_team": "ai-knowledge-engineering",
            "accountable_role": "data-owner",
            "retention_policy": "developer-candidate-review-or-delete-within-30-days",
            "privacy_scan_status": "pending-independent-evidence",
            "rights_status": "synthetic-only-no-external-content",
            "independent_review_evidence": [],
            "human_approval_evidence": [],
        },
        "exclusion_policy": {
            "golden_heldout": "forbidden",
            "training": "forbidden",
            "knowledge_retrieval": "forbidden",
            "customer_conversations": "forbidden",
        },
        "deletion_method": "delete-content-addressed-directory",
    }
    bundle_digest = hashlib.sha256(_canonical_json(base_manifest)).hexdigest()
    manifest = {**base_manifest, "bundle_digest": bundle_digest}
    bundle = RehearsalBundle(
        cases=case_tuple,
        cases_jsonl=cases_jsonl,
        manifest_json=_canonical_json(manifest) + b"\n",
        manifest=manifest,
        bundle_digest=bundle_digest,
    )
    verify_rehearsal_bundle_v2(
        manifest_bytes=bundle.manifest_json,
        cases_bytes=bundle.cases_jsonl,
        expected_digest=bundle.bundle_digest,
    )
    return bundle


def verify_rehearsal_bundle_v2(
    *,
    manifest_bytes: bytes,
    cases_bytes: bytes,
    expected_digest: str,
) -> dict[str, Any]:
    """Verify digest plus the semantic policy of every v2 case."""

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
        raise RegistryInvariantError("rehearsal v2 contains invalid JSON") from error

    if manifest.get("schema_version") != 2:
        raise RegistryInvariantError("rehearsal v2 manifest revision mismatch")
    if manifest.get("authority_bindings") != _AUTHORITY_BINDINGS:
        raise RegistryInvariantError("rehearsal v2 authority bindings mismatch")
    _sha256(manifest.get("generator_source_sha256", ""))
    if manifest.get("governance", {}).get("human_approval_evidence") != []:
        raise RegistryInvariantError("rehearsal v2 cannot contain synthetic approval evidence")
    if len(cases) != 100 or manifest.get("case_count") != len(cases):
        raise RegistryInvariantError("rehearsal v2 must contain exactly 100 cases")
    if len({case.get("case_id") for case in cases}) != len(cases):
        raise RegistryInvariantError("rehearsal v2 case IDs must be unique")
    suite_counts = dict(sorted(Counter(case.get("suite_id") for case in cases).items()))
    if manifest.get("suite_counts") != suite_counts:
        raise RegistryInvariantError("rehearsal v2 suite counts mismatch")
    family_count = len({case.get("split_family_id") for case in cases})
    if manifest.get("family_count") != family_count:
        raise RegistryInvariantError("rehearsal v2 family count mismatch")

    for case in cases:
        _verify_case(case)
    _verify_semantic_families(cases)
    return verified


def _verify_case(case: dict[str, Any]) -> None:
    required = {
        "case_id",
        "suite_id",
        "suite_revision",
        "rubric_revision",
        "conversation",
        "initial_context",
        "expected",
        "review",
        "split_family_id",
        "lineage",
        "allowed_use",
    }
    if not required.issubset(case):
        raise RegistryInvariantError("rehearsal v2 case is incomplete")
    review = case.get("review", {})
    lineage = case.get("lineage", {})
    if (
        case.get("allowed_use") != "evaluation"
        or review
        != {
            "status": "pending",
            "human_label": None,
            "reviewer_role": None,
            "adjudication_evidence": [],
        }
        or lineage.get("source_refs") != []
        or lineage.get("seed_refs")
        != [f"synthetic:{REHEARSAL_V2_GENERATOR_REVISION}"]
    ):
        raise RegistryInvariantError(
            "rehearsal v2 cases must remain pending, synthetic, and evaluation-only"
        )
    if (
        case.get("suite_revision") != REHEARSAL_V2_SUITE_REVISION
        or case.get("rubric_revision") != REHEARSAL_V2_RUBRIC_REVISION
    ):
        raise RegistryInvariantError("rehearsal v2 case authority revision mismatch")
    expected = case.get("expected", {})
    if expected.get("outcome") not in _ALLOWED_OUTCOMES:
        raise RegistryInvariantError("rehearsal v2 outcome is invalid")
    assertions = case.get("initial_context", {}).get("evaluation_assertions", {})
    if assertions.get("voice_dimensions") != list(_VOICE_DIMENSIONS):
        raise RegistryInvariantError("rehearsal v2 voice assertions are missing")


def _verify_semantic_families(cases: tuple[dict[str, Any], ...]) -> None:
    families_by_fact: dict[str, set[str]] = {}
    for case in cases:
        for claim in case.get("expected", {}).get("required_claims", []):
            text = claim.get("text", "")
            for marker, family in _SHARED_FACT_FAMILIES:
                if marker in text:
                    families_by_fact.setdefault(family, set()).add(case["split_family_id"])
    if any(len(families) != 1 for families in families_by_fact.values()):
        raise RegistryInvariantError("rehearsal v2 semantic variants cross split families")
    if len(families_by_fact) != len(_SHARED_FACT_FAMILIES):
        raise RegistryInvariantError("rehearsal v2 semantic family coverage is incomplete")


def _family_for(case: dict[str, Any]) -> str:
    claims = case["expected"]["required_claims"]
    if claims:
        text = claims[0]["text"]
        for marker, family in _SHARED_FACT_FAMILIES:
            if marker in text:
                return f"rehearsal-v2:family:{family}"
    suffix = case["split_family_id"].split(":", maxsplit=1)[-1]
    return f"rehearsal-v2:{suffix}"


def _add_voice_assertions(case: dict[str, Any]) -> None:
    outcome = case["expected"]["outcome"]
    policies = ["concise", "polite-vietnamese", "no-brand-impersonation"]
    if outcome in {"clarification_required", "refusal", "handoff_recommended"}:
        policies.append("state-limits-and-next-step")
    if outcome == "tool_proposal":
        policies.append("proposal-not-execution")
    case["initial_context"]["evaluation_assertions"] = {
        "voice_dimensions": list(_VOICE_DIMENSIONS),
        "minimum_dimension_candidate": 2,
        "response_policies": policies,
        "human_threshold_authority": "pending-product-brand-data-owner",
    }


def _correct_outcome_precedence(case: dict[str, Any], suite_index: int) -> None:
    expected = case["expected"]
    if case["suite_id"] == "retrieval-no-evidence":
        ambiguous_slots = {
            0: ["vehicle_model", "vehicle_variant"],
            9: ["vehicle_model", "vehicle_variant"],
            11: ["part_name", "vehicle_model"],
        }
        if suite_index in ambiguous_slots:
            expected["outcome"] = "clarification_required"
            expected["clarification_slots"] = ambiguous_slots[suite_index]
            expected["reason_code"] = "clarification_precedes_evidence_lookup"
    if case["suite_id"] != "tool-authorization":
        return
    tool = expected["tool"]
    if tool["authorization_decision"] != "allow":
        return
    complete_requests = {
        0: (
            "Đề xuất lịch kiểm tra tại trung tâm LAB-01 vào sáng mai.",
            {"service_type": "inspection", "location": "LAB-01", "slot": "tomorrow-am"},
        ),
        2: (
            "Tạo đề xuất gọi lại qua số đã xác minh lúc 9 giờ.",
            {"channel": "verified-phone", "slot": "09:00"},
        ),
        4: (
            "Đề xuất hủy lịch APPT-SYNTH-04 của chính tôi, chưa thực hiện ngay.",
            {"appointment_id": "APPT-SYNTH-04"},
        ),
        6: (
            "Đề xuất lái thử MẪU_THỬ_07 tại LAB-02 vào cuối tuần.",
            {"vehicle_model": "MẪU_THỬ_07", "location": "LAB-02", "slot": "weekend"},
        ),
        8: (
            "Tạo đề xuất đổi khu vực liên hệ của tôi sang LAB-SOUTH.",
            {"target_area": "LAB-SOUTH"},
        ),
    }
    prompt, arguments = complete_requests[suite_index]
    case["conversation"] = [{"role": "user", "content": prompt}]
    tool["arguments"] = arguments


def _add_typed_state_assertions(case: dict[str, Any]) -> None:
    expected = case["expected"]
    outcome = expected["outcome"]
    reason = expected["reason_code"]
    delta = expected["state_assertions"]["required_delta"]
    if outcome == "cancelled":
        delta.update({"task.status": "cancelled", "task.reason_code": reason})
    elif outcome == "failed_safely":
        status = (
            "reconciliation_required"
            if reason == "partial_commit_unknown"
            else "failed_safely"
        )
        delta.update({"task.status": status, "task.reason_code": reason})
    elif outcome == "handoff_recommended":
        delta.update({"handoff.status": "recommended", "handoff.reason_code": reason})


def _sha256(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise RegistryInvariantError("rehearsal v2 digest must be SHA-256 hex")
    return value


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
