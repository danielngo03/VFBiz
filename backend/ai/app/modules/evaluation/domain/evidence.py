from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from hashlib import sha256
from typing import cast

from app.modules.evaluation.domain.benchmark import (
    MAX_PERSISTED_LATENCY_MS,
    MAX_SAFE_JSON_INTEGER,
    AuthorityClass,
    BudgetPolicy,
)
from app.modules.evaluation.domain.canonical import canonical_json, digest_document
from app.modules.evaluation.domain.grader import GraderKind
from app.modules.evaluation.domain.plan import CalibrationBinding
from app.modules.evaluation.domain.validation import (
    is_bounded_text,
    is_finite_non_negative,
    is_fixed_usd,
    is_sha256,
)

_CASE_VALIDITY_FLAGS = frozenset(
    {
        "broken-case",
        "ambiguous-ground-truth",
        "contamination",
        "harness-mismatch",
        "reward-hacking",
        "format-avoidance",
        "missing-evidence",
        "runner-unavailable",
        "provider-timeout",
        "artifact-store-unavailable",
        "usage-unknown",
    }
)

_AUTHORITY_TOKEN = object()
MANDATORY_HARD_GATE_REVISIONS = frozenset(
    {
        "acl-leakage-v1",
        "citation-validity-v1",
        "pii-leakage-v1",
        "tool-authorization-v1",
    }
)


@dataclass(frozen=True, slots=True)
class EvaluationUsage:
    input_tokens: int
    output_tokens: int
    cost_usd: float

    def __post_init__(self) -> None:
        if (
            self.input_tokens < 0
            or self.output_tokens < 0
            or self.input_tokens > MAX_SAFE_JSON_INTEGER
            or self.output_tokens > MAX_SAFE_JSON_INTEGER
            or not is_fixed_usd(self.cost_usd)
        ):
            raise ValueError("INVALID_EVALUATION_USAGE")

    def add(self, other: EvaluationUsage) -> EvaluationUsage:
        return EvaluationUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cost_usd=float(
                (Decimal(str(self.cost_usd)) + Decimal(str(other.cost_usd))).quantize(
                    Decimal("0.000001")
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class MetricCaseOutcome:
    metric_revision: str
    slice: str
    value: float

    def __post_init__(self) -> None:
        if (
            not is_bounded_text(self.metric_revision, maximum=200)
            or not is_bounded_text(self.slice, maximum=200)
            or not math.isfinite(self.value)
        ):
            raise ValueError("INVALID_METRIC_CASE_OUTCOME")

    @property
    def canonical_document(self) -> dict[str, object]:
        return {
            "metric_revision": self.metric_revision,
            "slice": self.slice,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class GraderCaseOutcome:
    grader_revision: str
    outcome: str
    evidence_digest: str
    score: float | None = None

    def __post_init__(self) -> None:
        if (
            not is_bounded_text(self.grader_revision, maximum=200)
            or self.outcome not in {"pass", "fail", "abstain", "invalid"}
            or not is_sha256(self.evidence_digest)
            or (self.score is not None and not math.isfinite(self.score))
        ):
            raise ValueError("INVALID_GRADER_CASE_OUTCOME")

    @property
    def canonical_document(self) -> dict[str, object]:
        return {
            "evidence_digest": self.evidence_digest,
            "grader_revision": self.grader_revision,
            "outcome": self.outcome,
            "score": self.score,
        }


@dataclass(frozen=True, slots=True)
class EvaluationCaseResult:
    run_id: str
    case_id: str
    case_digest: str
    attempt: int
    status: str
    output_digest: str | None
    latency_ms: int
    usage: EvaluationUsage
    sanitized_trace_ref: str | None
    metric_outputs: tuple[MetricCaseOutcome, ...]
    grader_outputs: tuple[GraderCaseOutcome, ...]
    validity_flags: tuple[str, ...]
    result_digest: str

    def __post_init__(self) -> None:
        grader_revisions = tuple(outcome.grader_revision for outcome in self.grader_outputs)
        metric_bindings = tuple(
            (outcome.metric_revision, outcome.slice) for outcome in self.metric_outputs
        )
        if (
            not is_bounded_text(self.run_id, maximum=160)
            or not is_bounded_text(self.case_id, maximum=200)
            or not is_sha256(self.case_digest)
            or not 1 <= self.attempt <= 3
            or self.status not in {"valid", "invalid", "failed", "cancelled"}
            or (self.output_digest is not None and not is_sha256(self.output_digest))
            or self.latency_ms < 0
            or self.latency_ms > MAX_PERSISTED_LATENCY_MS
            or (
                self.sanitized_trace_ref is not None
                and (
                    not is_bounded_text(self.sanitized_trace_ref, maximum=500)
                    or "://" not in self.sanitized_trace_ref
                )
            )
            or len(set(grader_revisions)) != len(grader_revisions)
            or len(set(metric_bindings)) != len(metric_bindings)
            or len(set(self.validity_flags)) != len(self.validity_flags)
            or not set(self.validity_flags).issubset(_CASE_VALIDITY_FLAGS)
            or not is_sha256(self.result_digest)
        ):
            raise ValueError("INVALID_EVALUATION_CASE_RESULT")
        if self.status == "valid" and (
            self.output_digest is None or not self.grader_outputs or self.validity_flags
        ):
            raise ValueError("INVALID_VALID_CASE_RESULT")
        if self.status in {"failed", "cancelled"} and (
            self.output_digest is not None or self.grader_outputs
        ):
            raise ValueError("INVALID_TERMINAL_CASE_RESULT")
        if self.status == "invalid" and not self.validity_flags:
            raise ValueError("INVALID_CASE_REQUIRES_REASON")
        if self.result_digest != digest_document(self.semantic_document):
            raise ValueError("CASE_RESULT_DIGEST_MISMATCH")

    @property
    def semantic_document(self) -> dict[str, object]:
        return {
            "attempt": self.attempt,
            "case_digest": self.case_digest,
            "case_id": self.case_id,
            "grader_outputs": [outcome.canonical_document for outcome in self.grader_outputs],
            "latency_ms": self.latency_ms,
            "metric_outputs": [outcome.canonical_document for outcome in self.metric_outputs],
            "output_digest": self.output_digest,
            "run_id": self.run_id,
            "sanitized_trace_ref": self.sanitized_trace_ref,
            "status": self.status,
            "usage": {
                "cost_usd": self.usage.cost_usd,
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
            },
            "validity_flags": list(self.validity_flags),
        }

    @property
    def contract_document(self) -> dict[str, object]:
        return {**self.semantic_document, "result_digest": self.result_digest}

    @property
    def canonical_payload(self) -> str:
        return canonical_json(self.semantic_document)

    @classmethod
    def issue(
        cls,
        *,
        run_id: str,
        case_id: str,
        case_digest: str,
        attempt: int,
        status: str,
        output_digest: str | None,
        latency_ms: int,
        usage: EvaluationUsage,
        sanitized_trace_ref: str | None,
        metric_outputs: tuple[MetricCaseOutcome, ...],
        grader_outputs: tuple[GraderCaseOutcome, ...],
        validity_flags: tuple[str, ...] = (),
    ) -> EvaluationCaseResult:
        semantic_document: dict[str, object] = {
            "attempt": attempt,
            "case_digest": case_digest,
            "case_id": case_id,
            "grader_outputs": [outcome.canonical_document for outcome in grader_outputs],
            "latency_ms": latency_ms,
            "metric_outputs": [outcome.canonical_document for outcome in metric_outputs],
            "output_digest": output_digest,
            "run_id": run_id,
            "sanitized_trace_ref": sanitized_trace_ref,
            "status": status,
            "usage": {
                "cost_usd": usage.cost_usd,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            },
            "validity_flags": list(validity_flags),
        }
        return cls(
            run_id=run_id,
            case_id=case_id,
            case_digest=case_digest,
            attempt=attempt,
            status=status,
            output_digest=output_digest,
            latency_ms=latency_ms,
            usage=usage,
            sanitized_trace_ref=sanitized_trace_ref,
            metric_outputs=metric_outputs,
            grader_outputs=grader_outputs,
            validity_flags=validity_flags,
            result_digest=digest_document(semantic_document),
        )


@dataclass(frozen=True, slots=True)
class EvaluationSuiteAuthority:
    suite_id: str
    authority_class: AuthorityClass
    qualification_profile: str
    qualification_policy_digest: str
    case_bindings_digest: str
    case_composition_digest: str
    risk_taxonomy_digest: str
    provenance_digest: str
    provenance_status: str
    provenance_evidence_uri: str
    contamination_scan_digest: str
    contamination_status: str
    contamination_evidence_uri: str
    held_out: bool
    author_subject: str
    evaluator_subject: str
    release_owner_subject: str
    authority_digest: str

    def __post_init__(self) -> None:
        subjects = (
            self.author_subject,
            self.evaluator_subject,
            self.release_owner_subject,
        )
        if (
            not is_bounded_text(self.suite_id, maximum=200)
            or not is_bounded_text(self.qualification_profile, maximum=200)
            or any(
                not is_sha256(value)
                for value in (
                    self.qualification_policy_digest,
                    self.case_bindings_digest,
                    self.case_composition_digest,
                    self.risk_taxonomy_digest,
                    self.provenance_digest,
                    self.contamination_scan_digest,
                    self.authority_digest,
                )
            )
            or self.provenance_status != "verified"
            or not self.provenance_evidence_uri.startswith("evidence://")
            or self.contamination_status != "passed"
            or not self.contamination_evidence_uri.startswith("evidence://")
            or any(not is_bounded_text(subject, maximum=200) for subject in subjects)
            or len(set(subjects)) != 3
            or self.authority_digest != digest_document(self.semantic_document)
        ):
            raise ValueError("INVALID_EVALUATION_SUITE_AUTHORITY")

    @property
    def semantic_document(self) -> dict[str, object]:
        return {
            "authority_class": self.authority_class.value,
            "author_subject": self.author_subject,
            "case_bindings_digest": self.case_bindings_digest,
            "case_composition_digest": self.case_composition_digest,
            "contamination_evidence_uri": self.contamination_evidence_uri,
            "contamination_scan_digest": self.contamination_scan_digest,
            "contamination_status": self.contamination_status,
            "evaluator_subject": self.evaluator_subject,
            "held_out": self.held_out,
            "provenance_digest": self.provenance_digest,
            "provenance_evidence_uri": self.provenance_evidence_uri,
            "provenance_status": self.provenance_status,
            "qualification_policy_digest": self.qualification_policy_digest,
            "qualification_profile": self.qualification_profile,
            "release_owner_subject": self.release_owner_subject,
            "risk_taxonomy_digest": self.risk_taxonomy_digest,
            "subject_roles": {
                "author": "dataset-author",
                "evaluator": "independent-evaluator",
                "release_owner": "release-owner",
            },
            "suite_id": self.suite_id,
        }

    @property
    def contract_document(self) -> dict[str, object]:
        return {**self.semantic_document, "authority_digest": self.authority_digest}

    @classmethod
    def issue(
        cls,
        *,
        suite_id: str,
        authority_class: AuthorityClass,
        qualification_profile: str,
        qualification_policy_digest: str,
        case_bindings_digest: str,
        case_composition_digest: str,
        risk_taxonomy_digest: str,
        provenance_digest: str,
        provenance_status: str,
        provenance_evidence_uri: str,
        contamination_scan_digest: str,
        contamination_status: str,
        contamination_evidence_uri: str,
        held_out: bool,
        author_subject: str,
        evaluator_subject: str,
        release_owner_subject: str,
    ) -> EvaluationSuiteAuthority:
        values: dict[str, object] = {
            "authority_class": authority_class.value,
            "author_subject": author_subject,
            "case_bindings_digest": case_bindings_digest,
            "case_composition_digest": case_composition_digest,
            "contamination_evidence_uri": contamination_evidence_uri,
            "contamination_scan_digest": contamination_scan_digest,
            "contamination_status": contamination_status,
            "evaluator_subject": evaluator_subject,
            "held_out": held_out,
            "provenance_digest": provenance_digest,
            "provenance_evidence_uri": provenance_evidence_uri,
            "provenance_status": provenance_status,
            "qualification_policy_digest": qualification_policy_digest,
            "qualification_profile": qualification_profile,
            "release_owner_subject": release_owner_subject,
            "risk_taxonomy_digest": risk_taxonomy_digest,
            "subject_roles": {
                "author": "dataset-author",
                "evaluator": "independent-evaluator",
                "release_owner": "release-owner",
            },
            "suite_id": suite_id,
        }
        return cls(
            suite_id=suite_id,
            authority_class=authority_class,
            qualification_profile=qualification_profile,
            qualification_policy_digest=qualification_policy_digest,
            case_bindings_digest=case_bindings_digest,
            case_composition_digest=case_composition_digest,
            risk_taxonomy_digest=risk_taxonomy_digest,
            provenance_digest=provenance_digest,
            provenance_status=provenance_status,
            provenance_evidence_uri=provenance_evidence_uri,
            contamination_scan_digest=contamination_scan_digest,
            contamination_status=contamination_status,
            contamination_evidence_uri=contamination_evidence_uri,
            held_out=held_out,
            author_subject=author_subject,
            evaluator_subject=evaluator_subject,
            release_owner_subject=release_owner_subject,
            authority_digest=digest_document(values),
        )


def evaluation_case_bindings_digest(
    case_bindings: tuple[tuple[str, str], ...],
) -> str:
    ordered = tuple(sorted(case_bindings, key=lambda binding: binding[0]))
    return digest_document(
        {
            "case_bindings": [
                {"case_digest": case_digest, "case_id": case_id} for case_id, case_digest in ordered
            ]
        }
    )


@dataclass(frozen=True, slots=True)
class EvaluationSuiteSnapshot:
    suite_id: str
    suite_digest: str
    case_bindings: tuple[tuple[str, str], ...]
    authority_class: AuthorityClass
    qualification_profile: str
    qualification_policy_digest: str
    case_composition_digest: str
    risk_taxonomy_digest: str
    provenance_digest: str
    provenance_status: str
    provenance_evidence_uri: str
    contamination_scan_digest: str
    contamination_status: str
    contamination_evidence_uri: str
    held_out: bool
    author_subject: str
    evaluator_subject: str
    release_owner_subject: str
    authority_record_digest: str

    def __post_init__(self) -> None:
        case_ids = [case_id for case_id, _ in self.case_bindings]
        case_digests = [case_digest for _, case_digest in self.case_bindings]
        if (
            not is_bounded_text(self.suite_id, maximum=200)
            or not is_sha256(self.suite_digest)
            or not self.case_bindings
            or self.case_bindings
            != tuple(sorted(self.case_bindings, key=lambda binding: binding[0]))
            or len(set(case_ids)) != len(case_ids)
            or len(set(case_digests)) != len(case_digests)
            or any(
                not is_bounded_text(case_id, maximum=200) or not is_sha256(case_digest)
                for case_id, case_digest in self.case_bindings
            )
            or not is_bounded_text(self.qualification_profile, maximum=200)
            or not is_sha256(self.qualification_policy_digest)
            or not is_sha256(self.case_composition_digest)
            or not is_sha256(self.risk_taxonomy_digest)
            or not is_sha256(self.provenance_digest)
            or self.provenance_status != "verified"
            or not self.provenance_evidence_uri.startswith("evidence://")
            or not is_sha256(self.contamination_scan_digest)
            or not is_sha256(self.authority_record_digest)
            or self.contamination_status != "passed"
            or not self.contamination_evidence_uri.startswith("evidence://")
            or any(
                not is_bounded_text(subject, maximum=200)
                for subject in (
                    self.author_subject,
                    self.evaluator_subject,
                    self.release_owner_subject,
                )
            )
            or len(
                {
                    self.author_subject,
                    self.evaluator_subject,
                    self.release_owner_subject,
                }
            )
            != 3
            or (
                self.authority_class is AuthorityClass.VINFAST_ACCEPTANCE
                and (len(self.case_bindings) < 500 or not self.held_out)
            )
            or self.suite_digest != digest_document(self.semantic_document)
        ):
            raise ValueError("INVALID_EVALUATION_SUITE_SNAPSHOT")

    @property
    def semantic_document(self) -> dict[str, object]:
        return {
            "authority_class": self.authority_class.value,
            "authority_record_digest": self.authority_record_digest,
            "author_subject": self.author_subject,
            "case_bindings": [
                {"case_digest": case_digest, "case_id": case_id}
                for case_id, case_digest in self.case_bindings
            ],
            "case_composition_digest": self.case_composition_digest,
            "contamination_scan_digest": self.contamination_scan_digest,
            "contamination_status": self.contamination_status,
            "contamination_evidence_uri": self.contamination_evidence_uri,
            "evaluator_subject": self.evaluator_subject,
            "held_out": self.held_out,
            "provenance_digest": self.provenance_digest,
            "provenance_status": self.provenance_status,
            "provenance_evidence_uri": self.provenance_evidence_uri,
            "qualification_profile": self.qualification_profile,
            "qualification_policy_digest": self.qualification_policy_digest,
            "release_owner_subject": self.release_owner_subject,
            "risk_taxonomy_digest": self.risk_taxonomy_digest,
            "suite_id": self.suite_id,
        }

    @property
    def contract_document(self) -> dict[str, object]:
        return {
            **self.semantic_document,
            "suite_digest": self.suite_digest,
        }

    @classmethod
    def issue(
        cls,
        *,
        suite_id: str,
        case_bindings: tuple[tuple[str, str], ...],
        authority: EvaluationSuiteAuthority,
    ) -> EvaluationSuiteSnapshot:
        ordered = tuple(sorted(case_bindings, key=lambda binding: binding[0]))
        if (
            authority.suite_id != suite_id
            or authority.case_bindings_digest != evaluation_case_bindings_digest(ordered)
        ):
            raise ValueError("SUITE_AUTHORITY_BINDING_MISMATCH")
        document: dict[str, object] = {
            "authority_class": authority.authority_class.value,
            "authority_record_digest": authority.authority_digest,
            "author_subject": authority.author_subject,
            "case_bindings": [
                {"case_digest": case_digest, "case_id": case_id} for case_id, case_digest in ordered
            ],
            "case_composition_digest": authority.case_composition_digest,
            "contamination_scan_digest": authority.contamination_scan_digest,
            "contamination_status": authority.contamination_status,
            "contamination_evidence_uri": authority.contamination_evidence_uri,
            "evaluator_subject": authority.evaluator_subject,
            "held_out": authority.held_out,
            "provenance_digest": authority.provenance_digest,
            "provenance_status": authority.provenance_status,
            "provenance_evidence_uri": authority.provenance_evidence_uri,
            "qualification_profile": authority.qualification_profile,
            "qualification_policy_digest": authority.qualification_policy_digest,
            "release_owner_subject": authority.release_owner_subject,
            "risk_taxonomy_digest": authority.risk_taxonomy_digest,
            "suite_id": suite_id,
        }
        return cls(
            suite_id=suite_id,
            suite_digest=digest_document(document),
            case_bindings=ordered,
            authority_class=authority.authority_class,
            qualification_profile=authority.qualification_profile,
            qualification_policy_digest=authority.qualification_policy_digest,
            case_composition_digest=authority.case_composition_digest,
            risk_taxonomy_digest=authority.risk_taxonomy_digest,
            provenance_digest=authority.provenance_digest,
            provenance_status=authority.provenance_status,
            provenance_evidence_uri=authority.provenance_evidence_uri,
            contamination_scan_digest=authority.contamination_scan_digest,
            contamination_status=authority.contamination_status,
            contamination_evidence_uri=authority.contamination_evidence_uri,
            held_out=authority.held_out,
            author_subject=authority.author_subject,
            evaluator_subject=authority.evaluator_subject,
            release_owner_subject=authority.release_owner_subject,
            authority_record_digest=authority.authority_digest,
        )


@dataclass(frozen=True, slots=True)
class BaselinePolicySnapshot:
    policy_digest: str
    semantic_document: dict[str, object]

    def __post_init__(self) -> None:
        if set(self.semantic_document) != {
            "binary_interval",
            "composite_score_authoritative",
            "hard_gates",
            "operational_budgets",
            "paired_comparison",
            "policy_id",
            "protected_metrics",
            "revision",
            "waiver_policy",
        }:
            raise ValueError("INVALID_BASELINE_POLICY_SNAPSHOT")
        hard_gates_value = self.semantic_document.get("hard_gates")
        protected_metrics_value = self.semantic_document.get("protected_metrics")
        operational_value = self.semantic_document.get("operational_budgets")
        paired_value = self.semantic_document.get("paired_comparison")
        waiver_value = self.semantic_document.get("waiver_policy")
        if (
            not isinstance(hard_gates_value, list)
            or not isinstance(protected_metrics_value, list)
            or not isinstance(operational_value, dict)
            or not isinstance(paired_value, dict)
            or not isinstance(waiver_value, dict)
        ):
            raise ValueError("INVALID_BASELINE_POLICY_SNAPSHOT")
        hard_gates = cast(list[object], hard_gates_value)
        protected_metrics = cast(list[object], protected_metrics_value)
        operational = cast(dict[str, object], operational_value)
        paired = cast(dict[str, object], paired_value)
        waiver = cast(dict[str, object], waiver_value)
        if (
            not is_sha256(self.policy_digest)
            or self.policy_digest != digest_document(self.semantic_document)
            or not is_bounded_text(
                str(self.semantic_document.get("policy_id", "")),
                maximum=200,
            )
            or not is_bounded_text(
                str(self.semantic_document.get("revision", "")),
                maximum=200,
            )
            or not protected_metrics
            or self.semantic_document.get("binary_interval") != "wilson-95"
            or self.semantic_document.get("composite_score_authoritative") is not False
            or set(paired) != {"method", "samples", "confidence"}
            or paired.get("method") != "paired-bootstrap"
            or paired.get("samples") != 10000
            or paired.get("confidence") != 0.95
            or set(operational)
            != {
                "latency_p95_ms",
                "normalized_cost_usd",
                "provider_failure_rate",
            }
            or not _positive_number(operational.get("latency_p95_ms"))
            or not _non_negative_number(operational.get("normalized_cost_usd"))
            or not _unit_interval(operational.get("provider_failure_rate"))
            or set(waiver)
            != {
                "authority_contract_id",
                "requires_expiry",
                "requires_mitigation",
                "requires_owner",
            }
            or waiver.get("requires_owner") is not True
            or waiver.get("requires_expiry") is not True
            or waiver.get("requires_mitigation") is not True
            or not _absolute_uri(waiver.get("authority_contract_id"))
        ):
            raise ValueError("INVALID_BASELINE_POLICY_SNAPSHOT")
        metric_revisions: list[str] = []
        for protected_metric in protected_metrics:
            if not isinstance(protected_metric, dict):
                raise ValueError("INVALID_BASELINE_POLICY_PROTECTED_METRIC")
            metric = cast(dict[str, object], protected_metric)
            required_slices = metric.get("required_slices")
            if (
                set(metric)
                != {
                    "direction",
                    "metric_revision",
                    "non_inferiority_margin",
                    "require_protected_95_bound",
                    "required_slices",
                }
                or not is_bounded_text(
                    str(metric.get("metric_revision", "")),
                    maximum=200,
                )
                or metric.get("direction") not in {"higher-is-better", "lower-is-better"}
                or not _non_negative_number(metric.get("non_inferiority_margin"))
                or metric.get("require_protected_95_bound") is not True
                or not _valid_required_slices(required_slices)
            ):
                raise ValueError("INVALID_BASELINE_POLICY_PROTECTED_METRIC")
            metric_revisions.append(str(metric["metric_revision"]))
        if len(set(metric_revisions)) != len(metric_revisions):
            raise ValueError("INVALID_BASELINE_POLICY_PROTECTED_METRIC")
        gate_revisions: list[str] = []
        for gate in hard_gates:
            if not isinstance(gate, dict):
                raise ValueError("INVALID_BASELINE_POLICY_HARD_GATE")
            gate_document = cast(dict[str, object], gate)
            if (
                set(gate_document) != {"gate_revision", "required_value"}
                or not is_bounded_text(
                    str(gate_document.get("gate_revision", "")),
                    maximum=200,
                )
                or gate_document.get("required_value") != 0
            ):
                raise ValueError("INVALID_BASELINE_POLICY_HARD_GATE")
            gate_revisions.append(str(gate_document["gate_revision"]))
        if len(set(gate_revisions)) != len(
            gate_revisions
        ) or not MANDATORY_HARD_GATE_REVISIONS.issubset(gate_revisions):
            raise ValueError("MANDATORY_HARD_GATE_POLICY_INCOMPLETE")

    @property
    def hard_gate_revisions(self) -> tuple[str, ...]:
        hard_gates_value = self.semantic_document["hard_gates"]
        if not isinstance(hard_gates_value, list):
            raise ValueError("INVALID_BASELINE_POLICY_HARD_GATE")
        hard_gates = cast(list[object], hard_gates_value)
        return tuple(
            str(cast(dict[str, object], gate)["gate_revision"])
            for gate in hard_gates
            if isinstance(gate, dict)
        )

    @property
    def protected_metric_slices(self) -> dict[str, tuple[str, ...]]:
        value = self.semantic_document["protected_metrics"]
        if not isinstance(value, list):
            raise ValueError("INVALID_BASELINE_POLICY_PROTECTED_METRIC")
        result: dict[str, tuple[str, ...]] = {}
        for item in cast(list[object], value):
            if not isinstance(item, dict):
                raise ValueError("INVALID_BASELINE_POLICY_PROTECTED_METRIC")
            metric = cast(dict[str, object], item)
            slices = metric.get("required_slices")
            if not isinstance(slices, list) or any(
                not isinstance(slice_name, str) for slice_name in cast(list[object], slices)
            ):
                raise ValueError("INVALID_BASELINE_POLICY_PROTECTED_METRIC")
            result[str(metric["metric_revision"])] = tuple(cast(list[str], slices))
        return result

    @property
    def contract_document(self) -> dict[str, object]:
        return {**self.semantic_document, "policy_digest": self.policy_digest}

    @classmethod
    def issue(
        cls,
        semantic_document: dict[str, object],
    ) -> BaselinePolicySnapshot:
        return cls(
            policy_digest=digest_document(semantic_document),
            semantic_document=semantic_document,
        )


def _non_negative_number(value: object) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and is_finite_non_negative(float(value))
    )


def _positive_number(value: object) -> bool:
    return _non_negative_number(value) and float(cast(int | float, value)) > 0


def _unit_interval(value: object) -> bool:
    return _non_negative_number(value) and float(cast(int | float, value)) <= 1


def _absolute_uri(value: object) -> bool:
    return (
        isinstance(value, str)
        and is_bounded_text(value, maximum=500)
        and value.startswith("https://")
    )


def _valid_required_slices(value: object) -> bool:
    if not isinstance(value, list):
        return False
    items = cast(list[object], value)
    return (
        bool(items)
        and "all" in items
        and all(isinstance(item, str) and is_bounded_text(item, maximum=200) for item in items)
        and len(set(cast(list[str], items))) == len(items)
    )


@dataclass(frozen=True, slots=True)
class VerifiedEvidenceBundle:
    run_id: str
    plan_digest: str
    bundle_digest: str
    canonical_payload: str
    suite_snapshot_payload: str
    baseline_policy_payload: str
    _token: object

    def __post_init__(self) -> None:
        document = self.semantic_document
        if (
            self._token is not _AUTHORITY_TOKEN
            or not is_bounded_text(self.run_id, maximum=160)
            or not is_sha256(self.plan_digest)
            or not is_sha256(self.bundle_digest)
            or document.get("run_request_digest") != self.plan_digest
            or self.bundle_digest != f"sha256:{sha256(self.canonical_payload.encode()).hexdigest()}"
        ):
            raise ValueError("UNVERIFIED_EVALUATION_EVIDENCE")

    @property
    def semantic_document(self) -> dict[str, object]:
        document = cast(object, json.loads(self.canonical_payload))
        if not isinstance(document, dict):
            raise ValueError("UNVERIFIED_EVALUATION_EVIDENCE")
        return cast(dict[str, object], document)

    @property
    def contract_document(self) -> dict[str, object]:
        return {**self.semantic_document, "bundle_digest": self.bundle_digest}

    @property
    def authority_class(self) -> AuthorityClass:
        return AuthorityClass(str(self.semantic_document["authority_class"]))

    @property
    def recommendation(self) -> str:
        return str(self.semantic_document["recommendation"])

    @property
    def run_result_payload(self) -> str:
        result = self.semantic_document["run_result"]
        if not isinstance(result, dict):
            raise ValueError("INVALID_EVIDENCE_RUN_RESULT")
        return canonical_json(cast(dict[str, object], result))

    @property
    def candidate_release_id(self) -> str:
        candidate = self.semantic_document["candidate_release"]
        if not isinstance(candidate, dict):
            raise ValueError("INVALID_EVIDENCE_CANDIDATE")
        return str(cast(dict[str, object], candidate)["release_id"])

    @property
    def candidate_manifest_digest(self) -> str:
        candidate = self.semantic_document["candidate_release"]
        if not isinstance(candidate, dict):
            raise ValueError("INVALID_EVIDENCE_CANDIDATE")
        return str(cast(dict[str, object], candidate)["manifest_digest"])


def build_verified_evidence(
    *,
    run_id: str,
    plan_digest: str,
    authority_class: AuthorityClass,
    suite: EvaluationSuiteSnapshot,
    cases: tuple[EvaluationCaseResult, ...],
    required_metrics: tuple[str, ...],
    required_graders: tuple[str, ...],
    grader_kinds: tuple[tuple[str, str], ...],
    grader_calibrations: tuple[CalibrationBinding, ...],
    budget: BudgetPolicy,
    baseline_policy: BaselinePolicySnapshot,
    benchmark_definition_digest: str,
    candidate_release_id: str,
    candidate_manifest_digest: str,
    baseline_release_id: str | None,
    baseline_manifest_digest: str | None,
    created_at: datetime,
    started_at: datetime,
) -> VerifiedEvidenceBundle:
    if suite.authority_class is not authority_class:
        raise ValueError("EVIDENCE_SUITE_AUTHORITY_MISMATCH")
    if (
        created_at.tzinfo is None
        or created_at.utcoffset() is None
        or started_at.tzinfo is None
        or started_at.utcoffset() is None
        or started_at > created_at
    ):
        raise ValueError("EVIDENCE_CLOCK_MUST_BE_AWARE")
    digests = (
        plan_digest,
        benchmark_definition_digest,
        candidate_manifest_digest,
        baseline_policy.policy_digest,
    )
    if (
        not is_bounded_text(candidate_release_id, maximum=200)
        or any(not is_sha256(value) for value in digests)
        or (baseline_release_id is None) != (baseline_manifest_digest is None)
        or (
            baseline_release_id is not None
            and (
                not is_bounded_text(baseline_release_id, maximum=200)
                or baseline_manifest_digest is None
                or not is_sha256(baseline_manifest_digest)
            )
        )
        or not required_graders
        or not required_metrics
        or len(set(required_graders)) != len(required_graders)
        or len(set(required_metrics)) != len(required_metrics)
        or any(not is_bounded_text(revision, maximum=200) for revision in required_graders)
    ):
        raise ValueError("INVALID_EVIDENCE_BINDING")

    calibration_revisions = tuple(binding.grader_revision for binding in grader_calibrations)
    kind_by_revision = dict(grader_kinds)
    hard_gate_revisions = set(baseline_policy.hard_gate_revisions)
    if (
        len(set(calibration_revisions)) != len(calibration_revisions)
        or set(calibration_revisions) != set(required_graders)
        or len(kind_by_revision) != len(grader_kinds)
        or set(kind_by_revision) != set(required_graders)
        or any(
            kind not in {member.value for member in GraderKind}
            for kind in kind_by_revision.values()
        )
        or all(kind == GraderKind.MODEL_JUDGE.value for kind in kind_by_revision.values())
        or not hard_gate_revisions.issubset(required_graders)
        or any(
            binding.human_labelled_suite_digest is None
            or binding.calibrated_at is None
            or binding.expires_at is None
            or not (binding.calibrated_at <= created_at < binding.expires_at)
            for binding in grader_calibrations
        )
    ):
        raise ValueError("EVIDENCE_GRADER_AUTHORITY_INCOMPLETE")

    expected = dict(suite.case_bindings)
    observed: dict[str, EvaluationCaseResult] = {}
    aggregate = EvaluationUsage(0, 0, 0)
    duration_ms = 0
    hard_gate_failures: set[str] = set()
    for result in cases:
        if result.run_id != run_id:
            raise ValueError("EVIDENCE_CASE_IDENTITY_MISMATCH")
        if expected.get(result.case_id) != result.case_digest:
            raise ValueError("EVIDENCE_CASE_BINDING_MISMATCH")
        aggregate = aggregate.add(result.usage)
        duration_ms += result.latency_ms
        current = observed.get(result.case_id)
        if current is not None and result.attempt <= current.attempt:
            raise ValueError("EVIDENCE_CASE_ATTEMPT_ORDER_MISMATCH")
        observed[result.case_id] = result

    for result in observed.values():
        result_graders = {output.grader_revision for output in result.grader_outputs}
        result_metrics = {output.metric_revision for output in result.metric_outputs}
        if result_graders != set(required_graders):
            raise ValueError("EVIDENCE_REQUIRED_GRADER_SET_MISMATCH")
        if result_metrics != set(required_metrics):
            raise ValueError("EVIDENCE_REQUIRED_METRIC_SET_MISMATCH")
        hard_gate_failures.update(
            output.grader_revision
            for output in result.grader_outputs
            if (output.grader_revision in hard_gate_revisions and output.outcome != "pass")
        )

    if set(observed) != set(expected):
        raise ValueError("EVIDENCE_CASE_SET_INCOMPLETE")
    if any(result.status != "valid" for result in observed.values()):
        raise ValueError("EVIDENCE_CASE_SET_NOT_VALID")
    duration_seconds = float(Decimal(duration_ms) / Decimal(1000))
    if (
        aggregate.input_tokens > budget.max_input_tokens
        or aggregate.output_tokens > budget.max_output_tokens
        or duration_seconds > budget.max_duration_seconds
        or Decimal(str(aggregate.cost_usd)) > Decimal(str(budget.max_cost_usd))
    ):
        raise ValueError("EVALUATION_BUDGET_EXCEEDED")

    # Protected-metric non-inferiority and paired-baseline adjudication are not
    # derivable from candidate case outputs alone. Evidence may reject on an
    # observed hard-gate failure, but it never fabricates release acceptance.
    recommendation = "reject" if hard_gate_failures else "needs-human-decision"
    ordered_cases = sorted(observed.values(), key=lambda item: item.case_id)
    case_results_document: dict[str, object] = {
        "case_results": [result.result_digest for result in ordered_cases]
    }
    case_results_digest = digest_document(case_results_document)
    run_result_document: dict[str, object] = {
        "budget_usage": {
            "cost_usd": aggregate.cost_usd,
            "duration_seconds": duration_seconds,
            "input_tokens": aggregate.input_tokens,
            "output_tokens": aggregate.output_tokens,
        },
        "case_counts": {
            "cancelled": 0,
            "evaluated": len(observed),
            "expected": len(expected),
            "failed": 0,
            "invalid": 0,
            "valid": len(observed),
        },
        "case_results_digest": case_results_digest,
        "hard_gate_failures": sorted(hard_gate_failures),
        "metrics": _aggregate_metric_outcomes(
            tuple(ordered_cases),
            required_metrics,
            baseline_policy=baseline_policy,
        ),
        "request_digest": plan_digest,
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "completed_at": created_at.isoformat(),
        "state": "decision_ready",
    }
    evidence_digest = digest_document(
        {
            "baseline_policy_digest": baseline_policy.policy_digest,
            "case_results_digest": case_results_digest,
            "plan_digest": plan_digest,
            "suite_digest": suite.suite_digest,
        }
    )
    run_result_document["evidence_digest"] = evidence_digest
    run_result_digest = digest_document(run_result_document)
    sanitized_report_digest = digest_document(
        {
            "case_results_digest": case_results_digest,
            "evidence_digest": evidence_digest,
            "run_result_digest": run_result_digest,
        }
    )
    document: dict[str, object] = {
        "authority_class": authority_class.value,
        "baseline_policy_digest": baseline_policy.policy_digest,
        "baseline_release": (
            None
            if baseline_release_id is None
            else {
                "manifest_digest": baseline_manifest_digest,
                "release_id": baseline_release_id,
            }
        ),
        "benchmark_definition_digest": benchmark_definition_digest,
        "bundle_id": f"bundle:{sha256(run_id.encode()).hexdigest()}",
        "candidate_release": {
            "manifest_digest": candidate_manifest_digest,
            "release_id": candidate_release_id,
        },
        "case_results_digest": case_results_digest,
        "case_set_complete": True,
        "created_at": created_at.isoformat(),
        "grader_calibrations": [
            {
                "calibration_digest": binding.calibration_digest,
                "grader_revision": binding.grader_revision,
            }
            for binding in sorted(
                grader_calibrations,
                key=lambda item: item.grader_revision,
            )
        ],
        "hard_gate_failures": sorted(hard_gate_failures),
        "human_approval_included": False,
        "recommendation": recommendation,
        "required_grader_revisions": list(required_graders),
        "run_request_digest": plan_digest,
        "run_result": run_result_document,
        "run_result_digest": run_result_digest,
        "sanitized_report_digest": sanitized_report_digest,
        "suite_revision": {
            "suite_digest": suite.suite_digest,
            "suite_id": suite.suite_id,
        },
    }
    payload = canonical_json(document)
    return VerifiedEvidenceBundle(
        run_id=run_id,
        plan_digest=plan_digest,
        bundle_digest=f"sha256:{sha256(payload.encode()).hexdigest()}",
        canonical_payload=payload,
        suite_snapshot_payload=canonical_json(suite.semantic_document),
        baseline_policy_payload=canonical_json(baseline_policy.semantic_document),
        _token=_AUTHORITY_TOKEN,
    )


def _aggregate_metric_outcomes(
    cases: tuple[EvaluationCaseResult, ...],
    required_metrics: tuple[str, ...],
    *,
    baseline_policy: BaselinePolicySnapshot,
) -> list[dict[str, object]]:
    values: dict[tuple[str, str], list[Decimal]] = {}
    for result in cases:
        for outcome in result.metric_outputs:
            values.setdefault(
                (outcome.metric_revision, outcome.slice),
                [],
            ).append(Decimal(str(outcome.value)))
    observed = {revision for revision, _slice in values}
    if observed != set(required_metrics):
        raise ValueError("EVIDENCE_REQUIRED_METRIC_SET_MISMATCH")
    protected = baseline_policy.protected_metric_slices
    for revision, required_slices in protected.items():
        observed_slices = {
            slice_name for metric_revision, slice_name in values if metric_revision == revision
        }
        if not set(required_slices).issubset(observed_slices):
            raise ValueError("EVIDENCE_PROTECTED_METRIC_SLICE_MISSING")
    return [
        {
            "lower_95": (
                _wilson_95(samples)[0]
                if revision in protected and slice_name in protected[revision]
                else None
            ),
            "metric_revision": revision,
            "sample_size": len(samples),
            "slice": slice_name,
            "upper_95": (
                _wilson_95(samples)[1]
                if revision in protected and slice_name in protected[revision]
                else None
            ),
            "value": float(
                (sum(samples, Decimal(0)) / Decimal(len(samples))).quantize(
                    Decimal("0.000000000000001"),
                    rounding=ROUND_HALF_UP,
                )
            ),
        }
        for (revision, slice_name), samples in sorted(values.items())
    ]


def _wilson_95(samples: list[Decimal]) -> tuple[float, float]:
    if not samples or any(sample not in {Decimal(0), Decimal(1)} for sample in samples):
        raise ValueError("EVIDENCE_PROTECTED_METRIC_REQUIRES_BINARY_SAMPLES")
    with localcontext() as context:
        context.prec = 50
        sample_size = Decimal(len(samples))
        proportion = sum(samples, Decimal(0)) / sample_size
        z = Decimal("1.959963984540054")
        z_squared = Decimal("3.8414588206941254")
        denominator = Decimal(1) + (z_squared / sample_size)
        centre = proportion + (z_squared / (Decimal(2) * sample_size))
        margin = (
            z
            * (
                (proportion * (Decimal(1) - proportion) / sample_size)
                + (z_squared / (Decimal(4) * sample_size * sample_size))
            ).sqrt()
        )
        quantum = Decimal("0.000000000000001")
        lower = max(
            Decimal(0),
            (centre - margin) / denominator,
        ).quantize(quantum, rounding=ROUND_HALF_UP)
        upper = min(
            Decimal(1),
            (centre + margin) / denominator,
        ).quantize(quantum, rounding=ROUND_HALF_UP)
    return float(lower), float(upper)
