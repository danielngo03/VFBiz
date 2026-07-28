"""Golden candidate smoke generation use case."""

from datetime import UTC, datetime
from typing import Any

from app.modules.datasets.domain.golden import GoldenCase, GoldenSuite


def to_contract_candidate(case: GoldenCase) -> dict[str, Any]:
    """Create a schema-ready synthetic shell; it is never an adjudicated Golden case."""
    answer = case.suite is GoldenSuite.FACTUAL_CITATION
    clarification = case.suite in {
        GoldenSuite.INTENT_OOD,
        GoldenSuite.MULTI_TURN_CONTEXT,
    }
    outcome = "answer" if answer else "clarification_required" if clarification else "refusal"
    evidence_id = f"synthetic-evidence-{case.case_id.hex[:12]}"
    expected: dict[str, Any] = {
        "outcome": outcome,
        "required_claims": (
            [
                {
                    "claim_id": f"claim-{case.case_id.hex[:12]}",
                    "text": "SYNTHETIC_ONLY: grounded automotive fact placeholder.",
                    "citation_evidence_ids": [evidence_id],
                }
            ]
            if answer
            else []
        ),
        "forbidden_claims": ["Unsourced production fact"],
        "clarification_slots": ["vehicle_variant"] if clarification else [],
        "reason_code": None if answer else "synthetic_smoke_no_authoritative_fact",
        "tool": None,
        "state_assertions": {
            "required_delta": {},
            "forbidden_paths": ["customer.raw_vin", "customer.email"],
        },
    }
    snapshot = (
        {
            "release_id": "synthetic-smoke-release",
            "revision": "synthetic-v1",
            "effective_at": datetime(2026, 7, 28, tzinfo=UTC).isoformat(),
            "evidence_ids": [evidence_id],
        }
        if answer
        else None
    )
    gates = ["pii", "state-integrity"]
    if answer:
        gates.extend(["citation-membership", "revision-coherence", "claim-grounding"])
    return {
        "case_id": f"vivi-smoke-{case.case_id.hex}",
        "suite_id": case.suite.value,
        "suite_revision": "vivi-golden-v2-smoke-v1",
        "assistant_profile": "public_customer",
        "locale": "vi-VN",
        "market": "VN",
        "risk_domain": "general",
        "conversation": [
            {
                "role": "user",
                "content": f"SYNTHETIC_ONLY smoke prompt for {case.suite.value}",
            }
        ],
        "initial_context": {},
        "knowledge_snapshot": snapshot,
        "expected": expected,
        "hard_gates": gates,
        "rubric_revision": "vivi-voice-v0-candidate",
        "review": {
            "status": "pending",
            "human_label": None,
            "reviewer_role": None,
            "adjudication_evidence": [],
        },
        "split_family_id": case.split_family_id,
        "lineage": {
            "seed_refs": ["synthetic:vivi-golden-v2-smoke-v1"],
            "source_refs": [],
        },
        "allowed_use": "evaluation",
    }
