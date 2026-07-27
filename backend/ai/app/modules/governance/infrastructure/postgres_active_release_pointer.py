from typing import cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.governance.application.active_release_pointer import (
    ActiveReleasePointer,
    ReleasePointerTargetKind,
)

_CURRENT_POINTER_STATEMENT = text(
    """
    SELECT
        pointer.target_kind AS target_kind,
        activation.activation_id AS activation_id,
        candidate.content_sha256 AS candidate_sha256,
        static_safe.safe_release_id AS safe_release_id,
        COALESCE(
            activation.activation_envelope_sha256,
            static_safe.safe_release_envelope_sha256
        ) AS envelope_sha256,
        pointer.revision AS pointer_revision
    FROM ai_assistant_release_pointer AS pointer
    LEFT JOIN ai_assistant_release_activation AS activation
        ON activation.id = pointer.activation_record_id
    LEFT JOIN ai_assistant_release_candidate AS candidate
        ON candidate.id = activation.candidate_record_id
    LEFT JOIN ai_assistant_static_safe_release AS static_safe
        ON static_safe.id = pointer.static_safe_release_record_id
    WHERE pointer.assistant_profile = :assistant_profile
      AND pointer.environment = :environment
    """
)


class PostgresActiveReleasePointerAdapter:
    """Reads `ai_assistant_release_pointer`, a raw fact — not a verified release.

    See `ActiveReleasePointer`'s docstring: this table records whichever
    activation or static-safe release currently won the pointer CAS. It is
    not run through `ReleaseManifestResolver.resolve()`, so it carries no
    proof of gate/approval/promotion/live-control validity.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def current(
        self,
        *,
        assistant_profile: str,
        environment: str,
    ) -> ActiveReleasePointer | None:
        async with self._sessions() as session:
            result = await session.execute(
                _CURRENT_POINTER_STATEMENT,
                {"assistant_profile": assistant_profile, "environment": environment},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return ActiveReleasePointer(
            assistant_profile=assistant_profile,
            environment=environment,
            target_kind=cast(ReleasePointerTargetKind, row["target_kind"]),
            activation_id=row["activation_id"],
            candidate_sha256=row["candidate_sha256"],
            safe_release_id=row["safe_release_id"],
            envelope_sha256=row["envelope_sha256"],
            pointer_revision=row["pointer_revision"],
        )
