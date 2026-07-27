import json
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.governance.infrastructure.trusted_release_artifacts import (
    EvidenceAuthenticityRequest,
    ReleaseArtifactErrorCode,
    ReleaseArtifactInfrastructureError,
)


@dataclass(frozen=True, slots=True)
class _TrustReceipt:
    table: str
    reference: str
    revision: int


@dataclass(slots=True)
class _TrustReceiptCollector:
    receipts: set[_TrustReceipt]


class PostgresTrustedReleaseRegistry:
    """Read-only authority for release artifacts and evidence.

    Writes are deliberately owned by the maker-checker release transaction.
    Runtime callers can only resolve active, effective records.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        self._receipts: ContextVar[_TrustReceiptCollector | None] = ContextVar(
            f"trusted-release-receipts-{id(self)}",
            default=None,
        )

    def begin_freshness_scope(self) -> Token[_TrustReceiptCollector | None]:
        return self._receipts.set(_TrustReceiptCollector(receipts=set()))

    def end_freshness_scope(self, token: object) -> None:
        self._receipts.reset(cast(Token[_TrustReceiptCollector | None], token))

    async def read_sha256(self, artifact_ref: str) -> str | None:
        try:
            async with self._sessions() as session:
                row = (
                    (
                        await session.execute(
                            text(
                                """
                                SELECT artifact_sha256, revision
                                FROM ai_trusted_release_artifact
                                WHERE artifact_ref = :artifact_ref
                                  AND state = 'active'
                                  AND effective_at <= :now
                                  AND (expires_at IS NULL OR expires_at > :now)
                                """
                            ),
                            {"artifact_ref": artifact_ref, "now": datetime.now(UTC)},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
        except SQLAlchemyError as error:
            raise ReleaseArtifactInfrastructureError(
                ReleaseArtifactErrorCode.LOOKUP_FAILED,
                retryable=True,
            ) from error
        if row is None:
            return None
        self._record("artifact", artifact_ref, int(row["revision"]))
        return str(row["artifact_sha256"])

    async def verify(self, request: EvidenceAuthenticityRequest) -> bool:
        try:
            async with self._sessions() as session:
                revision = await session.scalar(
                    text(
                        """
                        SELECT revision
                        FROM ai_trusted_release_evidence
                        WHERE evidence_ref = :evidence_ref
                            AND evidence_kind = :evidence_kind
                            AND evidence_sha256 = :evidence_sha256
                            AND target_sha256 = :target_sha256
                            AND assistant_profile = :assistant_profile
                            AND environment = :environment
                            AND authority_role IS NOT DISTINCT FROM :authority_role
                            AND approver_subject IS NOT DISTINCT FROM :approver_subject
                            AND state = 'active'
                            AND effective_at <= :now
                          AND (expires_at IS NULL OR expires_at > :now)
                        """
                    ),
                    {
                        "evidence_ref": request.evidence_ref,
                        "evidence_kind": request.kind.value,
                        "evidence_sha256": request.evidence_sha256,
                        "target_sha256": request.target_sha256,
                        "assistant_profile": request.assistant_profile,
                        "environment": request.environment,
                        "authority_role": request.authority_role,
                        "approver_subject": request.approver_subject,
                        "now": datetime.now(UTC),
                    },
                )
        except SQLAlchemyError as error:
            raise ReleaseArtifactInfrastructureError(
                ReleaseArtifactErrorCode.EVIDENCE_FAILED,
                retryable=True,
            ) from error
        if revision is None:
            return False
        self._record("evidence", request.evidence_ref, int(revision))
        return True

    def _record(self, table: str, reference: str, revision: int) -> None:
        collector = self._receipts.get()
        if collector is None:
            return
        receipt = _TrustReceipt(table=table, reference=reference, revision=revision)
        collector.receipts.add(receipt)

    async def assert_fresh(self) -> None:
        collector = self._receipts.get()
        if collector is None:
            raise ReleaseArtifactInfrastructureError(
                ReleaseArtifactErrorCode.EVIDENCE_FAILED,
                retryable=False,
            )
        receipts = sorted(
            collector.receipts,
            key=lambda item: (item.table, item.reference, item.revision),
        )
        payload = json.dumps(
            [
                {
                    "kind": receipt.table,
                    "reference": receipt.reference,
                    "revision": receipt.revision,
                }
                for receipt in receipts
            ],
            separators=(",", ":"),
        )
        try:
            async with self._sessions() as session:
                all_fresh = await session.scalar(
                    text(
                        """
                        WITH expected AS (
                          SELECT *
                          FROM jsonb_to_recordset(CAST(:receipts AS jsonb))
                            AS item(kind text, reference text, revision bigint)
                        ),
                        observed AS (
                          SELECT 'artifact'::text AS kind,
                                 artifact_ref AS reference, revision
                          FROM ai_trusted_release_artifact
                          WHERE state = 'active'
                            AND effective_at <= :now
                            AND (expires_at IS NULL OR expires_at > :now)
                          UNION ALL
                          SELECT 'evidence'::text AS kind,
                                 evidence_ref AS reference, revision
                          FROM ai_trusted_release_evidence
                          WHERE state = 'active'
                            AND effective_at <= :now
                            AND (expires_at IS NULL OR expires_at > :now)
                        )
                        SELECT count(*) = (
                          SELECT count(*) FROM expected
                        )
                        FROM expected
                        JOIN observed USING (kind, reference, revision)
                        """
                    ),
                    {"receipts": payload, "now": datetime.now(UTC)},
                )
                if not all_fresh:
                    raise ReleaseArtifactInfrastructureError(
                        ReleaseArtifactErrorCode.EVIDENCE_FAILED,
                        retryable=True,
                    )
        except ReleaseArtifactInfrastructureError:
            raise
        except SQLAlchemyError as error:
            raise ReleaseArtifactInfrastructureError(
                ReleaseArtifactErrorCode.EVIDENCE_FAILED,
                retryable=True,
            ) from error

    async def revoke(
        self,
        *,
        registry_kind: str,
        reference: str,
        expected_revision: int,
        actor_subject: str,
        reason: str,
        idempotency_key: str,
    ) -> None:
        if registry_kind not in {"artifact", "evidence"}:
            raise ValueError("registry kind must be artifact or evidence")
        if expected_revision <= 0 or not all(
            value.strip() for value in (reference, actor_subject, reason, idempotency_key)
        ):
            raise ValueError("revocation requires bounded authority inputs")
        statement = (
            text(
                """
                UPDATE ai_trusted_release_artifact
                SET state = 'revoked', revision = revision + 1
                WHERE artifact_ref = :reference
                  AND state = 'active' AND revision = :expected_revision
                RETURNING revision
                """
            )
            if registry_kind == "artifact"
            else text(
                """
                UPDATE ai_trusted_release_evidence
                SET state = 'revoked', revision = revision + 1
                WHERE evidence_ref = :reference
                  AND state = 'active' AND revision = :expected_revision
                RETURNING revision
                """
            )
        )
        try:
            async with self._sessions() as session, session.begin():
                await session.execute(
                    text("SELECT set_config('vfbiz.release_actor', :value, true)"),
                    {"value": actor_subject},
                )
                await session.execute(
                    text("SELECT set_config('vfbiz.release_reason', :value, true)"),
                    {"value": reason},
                )
                await session.execute(
                    text("SELECT set_config('vfbiz.release_idempotency_key', :value, true)"),
                    {"value": idempotency_key},
                )
                new_revision = await session.scalar(
                    statement,
                    {
                        "reference": reference,
                        "expected_revision": expected_revision,
                    },
                )
                if new_revision is None:
                    replay = await session.scalar(
                        text(
                            """
                            SELECT EXISTS (
                              SELECT 1 FROM ai_trusted_release_registry_history
                              WHERE registry_kind = :kind
                                AND registry_ref = :reference
                                AND idempotency_key = :idempotency_key
                                AND from_revision = :expected_revision
                                AND actor_subject = :actor_subject
                                AND reason = :reason
                            )
                            """
                        ),
                        {
                            "kind": registry_kind,
                            "reference": reference,
                            "idempotency_key": idempotency_key,
                            "expected_revision": expected_revision,
                            "actor_subject": actor_subject,
                            "reason": reason,
                        },
                    )
                    if not replay:
                        raise ReleaseArtifactInfrastructureError(
                            ReleaseArtifactErrorCode.EVIDENCE_FAILED,
                            retryable=False,
                        )
        except ReleaseArtifactInfrastructureError:
            raise
        except SQLAlchemyError as error:
            raise ReleaseArtifactInfrastructureError(
                ReleaseArtifactErrorCode.EVIDENCE_FAILED,
                retryable=True,
            ) from error
