from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.evaluation.domain import (
    AuthorityClass,
    BaselinePolicySnapshot,
    BenchmarkDefinition,
    BudgetPolicy,
    EvaluationSuiteAuthority,
    EvaluationSuiteSnapshot,
    GraderCalibration,
    GraderDefinition,
    GraderKind,
    MetricDefinition,
    MetricDirection,
    canonical_json,
    digest_document,
)
from app.modules.evaluation.infrastructure.models import (
    EvaluationDefinitionReleaseRecord,
)


class EvaluationDefinitionRegistryError(RuntimeError):
    pass


class PostgresEvaluationDefinitionRegistry:
    """Read only, fail-closed access to immutable released definitions."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get_benchmark(
        self,
        benchmark_id: str,
        revision: str,
    ) -> BenchmarkDefinition | None:
        document = await self._read("benchmark", benchmark_id, revision)
        if document is None:
            return None
        budgets = _object(document, "budgets")
        return BenchmarkDefinition(
            benchmark_id=_text(document, "benchmark_id"),
            revision=_text(document, "revision"),
            authority_class=AuthorityClass(_text(document, "authority_class")),
            suite_id=_text(document, "suite_id"),
            suite_digest=_text(document, "suite_digest"),
            runner_image_digest=_text(document, "runner_image_digest"),
            harness_revision=_text(document, "harness_revision"),
            tool_simulator_revision=_optional_text(
                document,
                "tool_simulator_revision",
            ),
            metric_revisions=_text_tuple(document, "metric_revisions"),
            grader_revisions=_text_tuple(document, "grader_revisions"),
            environment_revision=_text(document, "environment_revision"),
            budgets=BudgetPolicy(
                max_input_tokens=_integer(budgets, "max_input_tokens"),
                max_output_tokens=_integer(budgets, "max_output_tokens"),
                max_duration_seconds=_integer(
                    budgets,
                    "max_duration_seconds",
                ),
                max_cost_usd=_number(budgets, "max_cost_usd"),
            ),
            baseline_policy_digest=_text(
                document,
                "baseline_policy_digest",
            ),
            max_attempts=_integer(document, "max_attempts"),
            retryable_failure_codes=_text_tuple(
                document,
                "retryable_failure_codes",
            ),
            definition_digest=_text(document, "definition_digest"),
        )

    async def get_metric(self, revision: str) -> MetricDefinition | None:
        document = await self._read("metric", revision, revision)
        if document is None:
            return None
        return MetricDefinition(
            revision=_text(document, "revision"),
            direction=MetricDirection(_text(document, "direction")),
            required_slices=_text_tuple(document, "required_slices"),
            definition_digest=_text(document, "definition_digest"),
        )

    async def get_grader(self, revision: str) -> GraderDefinition | None:
        document = await self._read("grader", revision, revision)
        if document is None:
            return None
        return GraderDefinition(
            revision=_text(document, "revision"),
            kind=GraderKind(_text(document, "kind")),
            definition_digest=_text(document, "definition_digest"),
            implementation_digest=_text(document, "implementation_digest"),
            calibration_required=_boolean(
                document,
                "calibration_required",
            ),
        )

    async def get_calibration(
        self,
        grader_revision: str,
    ) -> GraderCalibration | None:
        document = await self._read_latest("calibration", grader_revision)
        if document is None:
            return None
        matrix = _object(document, "confusion_matrix")
        slices = _object_list(document, "slice_metrics")
        return GraderCalibration(
            grader_revision=_text(document, "grader_revision"),
            grader_definition_digest=_text(
                document,
                "grader_definition_digest",
            ),
            implementation_digest=_text(
                document,
                "implementation_digest",
            ),
            calibrated_at=_timestamp(document, "calibrated_at"),
            expires_at=_timestamp(document, "expires_at"),
            evidence_digest=_text(document, "evidence_digest"),
            human_labelled_suite_digest=_text(
                document,
                "human_labelled_suite_digest",
            ),
            sample_size=_integer(document, "sample_size"),
            confusion_matrix=(
                _integer(matrix, "true_positive"),
                _integer(matrix, "true_negative"),
                _integer(matrix, "false_positive"),
                _integer(matrix, "false_negative"),
            ),
            balanced_accuracy=_number(document, "balanced_accuracy"),
            f1=_number(document, "f1"),
            slice_metrics=tuple(
                (
                    _text(item, "slice"),
                    _integer(item, "sample_size"),
                    _number(item, "balanced_accuracy"),
                    _number(item, "f1"),
                    _integer(
                        _object(item, "confusion_matrix"),
                        "true_positive",
                    ),
                    _integer(
                        _object(item, "confusion_matrix"),
                        "true_negative",
                    ),
                    _integer(
                        _object(item, "confusion_matrix"),
                        "false_positive",
                    ),
                    _integer(
                        _object(item, "confusion_matrix"),
                        "false_negative",
                    ),
                )
                for item in slices
            ),
        )

    async def get_suite(
        self,
        suite_id: str,
        suite_digest: str,
    ) -> EvaluationSuiteSnapshot | None:
        document = await self._read("suite", suite_id, suite_digest)
        if document is None:
            return None
        bindings = _object_list(document, "case_bindings")
        authority_digest = _text(document, "authority_record_digest")
        authority_document = await self._read(
            "suite-authority",
            suite_id,
            authority_digest,
        )
        if authority_document is None:
            raise EvaluationDefinitionRegistryError(
                "released suite authority is unavailable"
            )
        authority = EvaluationSuiteAuthority(
            suite_id=_text(authority_document, "suite_id"),
            authority_class=AuthorityClass(
                _text(authority_document, "authority_class")
            ),
            qualification_profile=_text(
                authority_document,
                "qualification_profile",
            ),
            qualification_policy_digest=_text(
                authority_document,
                "qualification_policy_digest",
            ),
            case_bindings_digest=_text(
                authority_document,
                "case_bindings_digest",
            ),
            case_composition_digest=_text(
                authority_document,
                "case_composition_digest",
            ),
            risk_taxonomy_digest=_text(
                authority_document,
                "risk_taxonomy_digest",
            ),
            provenance_digest=_text(authority_document, "provenance_digest"),
            provenance_status=_text(authority_document, "provenance_status"),
            provenance_evidence_uri=_text(
                authority_document,
                "provenance_evidence_uri",
            ),
            contamination_scan_digest=_text(
                authority_document,
                "contamination_scan_digest",
            ),
            contamination_status=_text(
                authority_document,
                "contamination_status",
            ),
            contamination_evidence_uri=_text(
                authority_document,
                "contamination_evidence_uri",
            ),
            held_out=_boolean(authority_document, "held_out"),
            author_subject=_text(authority_document, "author_subject"),
            evaluator_subject=_text(authority_document, "evaluator_subject"),
            release_owner_subject=_text(
                authority_document,
                "release_owner_subject",
            ),
            authority_digest=authority_digest,
        )
        suite = EvaluationSuiteSnapshot.issue(
            suite_id=_text(document, "suite_id"),
            case_bindings=tuple(
                (
                    _text(binding, "case_id"),
                    _text(binding, "case_digest"),
                )
                for binding in bindings
            ),
            authority=authority,
        )
        if (
            suite.suite_id != suite_id
            or suite.suite_digest != suite_digest
            or _text(document, "suite_digest") != suite_digest
        ):
            raise EvaluationDefinitionRegistryError("released suite identity mismatch")
        return suite

    async def get_baseline_policy(
        self,
        policy_digest: str,
    ) -> BaselinePolicySnapshot | None:
        document = await self._read_latest(
            "baseline-policy",
            policy_digest,
        )
        if document is None:
            return None
        semantic = {key: value for key, value in document.items() if key != "policy_digest"}
        policy = BaselinePolicySnapshot.issue(semantic)
        if (
            policy.policy_digest != policy_digest
            or _text(document, "policy_digest") != policy_digest
        ):
            raise EvaluationDefinitionRegistryError("released baseline policy identity mismatch")
        return policy

    async def _read(
        self,
        kind: str,
        key: str,
        revision: str,
    ) -> dict[str, object] | None:
        async with self._sessions() as session:
            record = await session.scalar(
                select(EvaluationDefinitionReleaseRecord).where(
                    EvaluationDefinitionReleaseRecord.definition_kind == kind,
                    EvaluationDefinitionReleaseRecord.definition_key == key,
                    EvaluationDefinitionReleaseRecord.revision == revision,
                    EvaluationDefinitionReleaseRecord.revoked_at.is_(None),
                )
            )
        return (
            None
            if record is None
            else _verified_document(
                record,
                expected_kind=kind,
                expected_key=key,
                expected_revision=revision,
            )
        )

    async def _read_latest(
        self,
        kind: str,
        key: str,
    ) -> dict[str, object] | None:
        async with self._sessions() as session:
            records = (
                await session.scalars(
                    select(EvaluationDefinitionReleaseRecord)
                    .where(
                        EvaluationDefinitionReleaseRecord.definition_kind == kind,
                        EvaluationDefinitionReleaseRecord.definition_key == key,
                        EvaluationDefinitionReleaseRecord.revoked_at.is_(None),
                    )
                    .order_by(EvaluationDefinitionReleaseRecord.released_at.desc())
                    .limit(2)
                )
            ).all()
        if len(records) > 1:
            raise EvaluationDefinitionRegistryError("multiple active released definitions")
        return (
            None
            if not records
            else _verified_document(
                records[0],
                expected_kind=kind,
                expected_key=key,
                expected_revision=records[0].revision,
            )
        )


def _verified_document(
    record: EvaluationDefinitionReleaseRecord,
    *,
    expected_kind: str,
    expected_key: str,
    expected_revision: str,
) -> dict[str, object]:
    value = cast(object, json.loads(record.canonical_payload))
    if not isinstance(value, dict):
        raise EvaluationDefinitionRegistryError("released definition must be an object")
    document = cast(dict[str, object], value)
    if (
        record.definition_kind != expected_kind
        or record.definition_key != expected_key
        or record.revision != expected_revision
        or canonical_json(document) != record.canonical_payload
        or digest_document(document) != record.content_digest
    ):
        raise EvaluationDefinitionRegistryError("released definition digest mismatch")
    identity = _definition_identity(record.definition_kind, document)
    if identity != (record.definition_key, record.revision):
        raise EvaluationDefinitionRegistryError("released definition identity mismatch")
    return document


def _definition_identity(
    kind: str,
    document: dict[str, object],
) -> tuple[str, str]:
    if kind == "benchmark":
        return _text(document, "benchmark_id"), _text(document, "revision")
    if kind in {"metric", "grader"}:
        revision = _text(document, "revision")
        return revision, revision
    if kind == "calibration":
        return (
            _text(document, "grader_revision"),
            _text(document, "evidence_digest"),
        )
    if kind == "suite":
        return _text(document, "suite_id"), _text(document, "suite_digest")
    if kind == "suite-authority":
        return _text(document, "suite_id"), _text(document, "authority_digest")
    if kind == "baseline-policy":
        digest = _text(document, "policy_digest")
        return digest, digest
    raise EvaluationDefinitionRegistryError("released definition kind is unsupported")


def _value(document: dict[str, object], key: str) -> object:
    if key not in document:
        raise EvaluationDefinitionRegistryError(f"released definition missing {key}")
    return document[key]


def _text(document: dict[str, object], key: str) -> str:
    value = _value(document, key)
    if not isinstance(value, str):
        raise EvaluationDefinitionRegistryError(f"released definition {key} must be text")
    return value


def _optional_text(
    document: dict[str, object],
    key: str,
) -> str | None:
    value = _value(document, key)
    if value is not None and not isinstance(value, str):
        raise EvaluationDefinitionRegistryError(f"released definition {key} must be optional text")
    return value


def _integer(document: dict[str, object], key: str) -> int:
    value = _value(document, key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise EvaluationDefinitionRegistryError(f"released definition {key} must be integer")
    return value


def _number(document: dict[str, object], key: str) -> float:
    value = _value(document, key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise EvaluationDefinitionRegistryError(f"released definition {key} must be numeric")
    return float(value)


def _boolean(document: dict[str, object], key: str) -> bool:
    value = _value(document, key)
    if not isinstance(value, bool):
        raise EvaluationDefinitionRegistryError(f"released definition {key} must be boolean")
    return value


def _object(
    document: dict[str, object],
    key: str,
) -> dict[str, object]:
    value = _value(document, key)
    if not isinstance(value, dict):
        raise EvaluationDefinitionRegistryError(f"released definition {key} must be object")
    return cast(dict[str, object], value)


def _object_list(
    document: dict[str, object],
    key: str,
) -> list[dict[str, object]]:
    value = _value(document, key)
    if not isinstance(value, list) or any(
        not isinstance(item, dict) for item in cast(list[object], value)
    ):
        raise EvaluationDefinitionRegistryError(f"released definition {key} must be object list")
    return cast(list[dict[str, object]], value)


def _text_tuple(
    document: dict[str, object],
    key: str,
) -> tuple[str, ...]:
    value = _value(document, key)
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in cast(list[object], value)
    ):
        raise EvaluationDefinitionRegistryError(f"released definition {key} must be text list")
    return tuple(cast(list[str], value))


def _timestamp(document: dict[str, object], key: str) -> datetime:
    value = _text(document, key)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise EvaluationDefinitionRegistryError(
            f"released definition {key} must be timestamp"
        ) from error
    return parsed
