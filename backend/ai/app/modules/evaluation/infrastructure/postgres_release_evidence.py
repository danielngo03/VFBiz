from collections.abc import Mapping
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.evaluation.application import AssistantReleaseEvidenceSnapshot
from app.modules.evaluation.infrastructure.models import (
    EvaluationEvidenceBundleRecord,
    EvaluationRunRecord,
)


class PostgresAssistantReleaseEvidenceReader:
    """Read the content-free binding from immutable evaluation authority rows."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get_for_run(
        self,
        run_id: str,
    ) -> AssistantReleaseEvidenceSnapshot | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(EvaluationRunRecord, EvaluationEvidenceBundleRecord)
                    .join(
                        EvaluationEvidenceBundleRecord,
                        EvaluationEvidenceBundleRecord.run_key == EvaluationRunRecord.run_key,
                    )
                    .where(EvaluationRunRecord.run_key == run_id)
                )
            ).one_or_none()
        if row is None:
            return None
        run, bundle = row
        document = _mapping(bundle.canonical_document)
        candidate = _mapping(document.get("candidate_release"))
        run_result = _mapping(document.get("run_result"))
        return AssistantReleaseEvidenceSnapshot(
            run_id=_string(run.run_key) or "",
            run_state=run.status,
            run_evidence_bundle_digest=run.evidence_bundle_digest,
            run_candidate_release_id=run.candidate_release_ref,
            run_candidate_manifest_digest=run.candidate_manifest_digest,
            bundle_run_id=bundle.run_key,
            bundle_digest=bundle.bundle_digest,
            bundle_authority_class=bundle.authority_class,
            bundle_recommendation=bundle.recommendation,
            document_bundle_digest=_string(document.get("bundle_digest")),
            document_authority_class=_string(document.get("authority_class")),
            document_recommendation=_string(document.get("recommendation")),
            document_human_approval_included=_boolean(document.get("human_approval_included")),
            document_candidate_release_id=_string(candidate.get("release_id")),
            document_candidate_manifest_digest=_string(candidate.get("manifest_digest")),
            document_run_id=_string(run_result.get("run_id")),
            document_run_state=_string(run_result.get("state")),
        )


def _mapping(value: object) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else {}


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _boolean(value: object) -> bool | None:
    return value if isinstance(value, bool) else None
