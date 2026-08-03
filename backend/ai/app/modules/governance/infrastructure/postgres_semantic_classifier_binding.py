from typing import cast

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.governance.application import (
    SemanticClassifierBindingRecord,
    SemanticClassifierBindingState,
)
from app.modules.governance.domain import SemanticClassifierReleaseBinding
from app.modules.governance.infrastructure.release_authority_schema import (
    JsonSchemaAuthorityValidator,
)


class SemanticClassifierBindingPersistenceError(RuntimeError):
    """The binding authority could not be read safely."""


class PostgresSemanticClassifierBindingStore:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        schema_validator: JsonSchemaAuthorityValidator,
    ) -> None:
        self._sessions = sessions
        self._schema_validator = schema_validator

    async def get(
        self,
        *,
        activation_id: str,
        activation_envelope_sha256: str,
    ) -> SemanticClassifierBindingRecord | None:
        try:
            async with self._sessions() as session:
                row = (
                    (
                        await session.execute(
                            text(
                                """
                                SELECT canonical_document, state, revision
                                FROM ai_semantic_classifier_binding
                                WHERE activation_record_id =
                                      CAST(:activation_id AS uuid)
                                  AND activation_envelope_sha256 =
                                      :activation_envelope_sha256
                                """
                            ),
                            {
                                "activation_id": activation_id,
                                "activation_envelope_sha256": (
                                    activation_envelope_sha256
                                ),
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
        except (SQLAlchemyError, ValueError) as error:
            raise SemanticClassifierBindingPersistenceError(
                "SEMANTIC_CLASSIFIER_BINDING_READ_FAILED"
            ) from error
        if row is None:
            return None
        try:
            state = SemanticClassifierBindingState(str(row["state"]))
            binding = SemanticClassifierReleaseBinding(
                cast(dict[str, object], row["canonical_document"]),
                schema_validator=self._schema_validator,
            )
            return SemanticClassifierBindingRecord(
                binding=binding,
                state=state,
                revision=int(row["revision"]),
            )
        except (TypeError, ValueError) as error:
            raise SemanticClassifierBindingPersistenceError(
                "SEMANTIC_CLASSIFIER_BINDING_INVALID"
            ) from error
