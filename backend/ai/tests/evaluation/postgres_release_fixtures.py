from datetime import UTC, datetime
from typing import cast

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.evaluation.domain import (
    AuthorityClass,
    EvaluationSuiteAuthority,
    canonical_json,
    digest_document,
    evaluation_case_bindings_digest,
)
from app.modules.evaluation.infrastructure.models import (
    EvaluationDefinitionReleaseRecord,
)


async def release_plan_definitions(
    sessions: async_sessionmaker[AsyncSession],
    plan_document: dict[str, object],
    *,
    suite_document: dict[str, object] | None = None,
    policy_document: dict[str, object] | None = None,
) -> None:
    benchmark_digest = str(plan_document["benchmarkDefinitionDigest"])
    policy_digest = str(plan_document["baselinePolicyDigest"])
    suite = cast(dict[str, object], plan_document["suite"])
    if suite_document is None:
        raise ValueError("suite_document is required for governed release fixtures")
    raw_bindings = cast(list[dict[str, object]], suite_document["case_bindings"])
    bindings = tuple(
        (str(binding["case_id"]), str(binding["case_digest"]))
        for binding in raw_bindings
    )
    suite_authority = EvaluationSuiteAuthority.issue(
        suite_id=str(suite_document["suite_id"]),
        authority_class=AuthorityClass(str(suite_document["authority_class"])),
        qualification_profile=str(suite_document["qualification_profile"]),
        qualification_policy_digest=str(
            suite_document["qualification_policy_digest"]
        ),
        case_bindings_digest=evaluation_case_bindings_digest(bindings),
        case_composition_digest=str(suite_document["case_composition_digest"]),
        risk_taxonomy_digest=str(suite_document["risk_taxonomy_digest"]),
        provenance_digest=str(suite_document["provenance_digest"]),
        provenance_status=str(suite_document["provenance_status"]),
        provenance_evidence_uri=str(
            suite_document["provenance_evidence_uri"]
        ),
        contamination_scan_digest=str(
            suite_document["contamination_scan_digest"]
        ),
        contamination_status=str(suite_document["contamination_status"]),
        contamination_evidence_uri=str(
            suite_document["contamination_evidence_uri"]
        ),
        held_out=bool(suite_document["held_out"]),
        author_subject=str(suite_document["author_subject"]),
        evaluator_subject=str(suite_document["evaluator_subject"]),
        release_owner_subject=str(suite_document["release_owner_subject"]),
    )
    if (
        suite_authority.authority_digest
        != suite_document["authority_record_digest"]
    ):
        raise ValueError("suite authority fixture digest mismatch")
    budgets = cast(dict[str, object], plan_document["budgets"])
    attempt_policy = cast(dict[str, object], plan_document["attemptPolicy"])
    grader_kinds = {
        str(item["revision"]): str(item["kind"])
        for item in cast(
            list[dict[str, object]],
            plan_document["graderKinds"],
        )
    }
    calibrations = {
        str(item["graderRevision"]): item
        for item in cast(
            list[dict[str, object]],
            plan_document["graderCalibrations"],
        )
    }
    documents: list[tuple[str, str, str, dict[str, object]]] = [
        (
            "benchmark",
            f"fixture-{benchmark_digest[-12:]}",
            "v1",
            {
                "authority_class": plan_document["authorityClass"],
                "baseline_policy_digest": policy_digest,
                "benchmark_id": f"fixture-{benchmark_digest[-12:]}",
                "budgets": {
                    "max_cost_usd": budgets["maxCostUsd"],
                    "max_duration_seconds": budgets["maxDurationSeconds"],
                    "max_input_tokens": budgets["maxInputTokens"],
                    "max_output_tokens": budgets["maxOutputTokens"],
                },
                "definition_digest": benchmark_digest,
                "environment_revision": plan_document["environmentRevision"],
                "grader_revisions": plan_document["graderRevisions"],
                "harness_revision": plan_document["harnessRevision"],
                "max_attempts": attempt_policy["maxAttempts"],
                "metric_revisions": plan_document["metricRevisions"],
                "retryable_failure_codes": attempt_policy[
                    "retryableFailureCodes"
                ],
                "revision": "v1",
                "runner_image_digest": plan_document["runnerImageDigest"],
                "suite_digest": suite["digest"],
                "suite_id": suite["id"],
                "tool_simulator_revision": plan_document[
                    "toolSimulatorRevision"
                ],
            },
        ),
        (
            "suite-authority",
            str(suite["id"]),
            suite_authority.authority_digest,
            suite_authority.contract_document,
        ),
        (
            "suite",
            str(suite["id"]),
            str(suite["digest"]),
            suite_document,
        ),
        (
            "baseline-policy",
            policy_digest,
            policy_digest,
            policy_document or {"policy_digest": policy_digest},
        ),
    ]
    documents.extend(
        ("metric", revision, revision, {"revision": revision})
        for revision in cast(list[str], plan_document["metricRevisions"])
    )
    for revision in cast(list[str], plan_document["graderRevisions"]):
        binding = calibrations[revision]
        documents.append(
            (
                "grader",
                revision,
                revision,
                {
                    "calibration_required": True,
                    "definition_digest": binding["definitionDigest"],
                    "implementation_digest": binding[
                        "implementationDigest"
                    ],
                    "kind": grader_kinds[revision],
                    "revision": revision,
                },
            )
        )
        documents.append(
            (
                "calibration",
                revision,
                str(binding["calibrationDigest"]),
                {
                    "balanced_accuracy": 1,
                    "calibrated_at": binding["calibratedAt"],
                    "confusion_matrix": {
                        "false_negative": 0,
                        "false_positive": 0,
                        "true_negative": 15,
                        "true_positive": 15,
                    },
                    "evidence_digest": binding["calibrationDigest"],
                    "expires_at": binding["expiresAt"],
                    "f1": 1,
                    "grader_definition_digest": binding[
                        "definitionDigest"
                    ],
                    "grader_revision": revision,
                    "human_labelled_suite_digest": binding[
                        "humanLabelledSuiteDigest"
                    ],
                    "implementation_digest": binding[
                        "implementationDigest"
                    ],
                    "sample_size": 30,
                    "slice_metrics": [
                        {
                            "balanced_accuracy": 1,
                            "confusion_matrix": {
                                "false_negative": 0,
                                "false_positive": 0,
                                "true_negative": 15,
                                "true_positive": 15,
                            },
                            "f1": 1,
                            "sample_size": 30,
                            "slice": slice_name,
                        }
                        for slice_name in ("all", "high-risk")
                    ],
                },
            )
        )
    async with sessions() as session, session.begin():
        for kind, key, revision, document in documents:
            payload = canonical_json(document)
            await session.execute(
                insert(EvaluationDefinitionReleaseRecord)
                .values(
                    definition_kind=kind,
                    definition_key=key,
                    revision=revision,
                    content_digest=digest_document(document),
                    canonical_payload=payload,
                    release_evidence_uri=(
                        "evidence://evaluation-definition/integration"
                    ),
                    released_by_subject="subject:integration-release-owner",
                    released_at=datetime(2026, 7, 31, tzinfo=UTC),
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        "definition_kind",
                        "definition_key",
                        "revision",
                    ]
                )
            )
