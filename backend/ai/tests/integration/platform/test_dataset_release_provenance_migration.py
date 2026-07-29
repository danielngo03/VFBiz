import asyncio
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)

AI_ROOT = Path(__file__).resolve().parents[3]


def run_alembic(operation: str, revision: str) -> None:
    configuration = Config(str(AI_ROOT / "alembic.ini"))
    if operation == "upgrade":
        command.upgrade(configuration, revision)
    elif operation == "downgrade":
        command.downgrade(configuration, revision)
    else:  # pragma: no cover - fixed helper contract
        raise ValueError(f"unsupported Alembic operation: {operation}")


async def seed_source_and_fetch(
    sessions: async_sessionmaker[AsyncSession],
    *,
    source_id: UUID,
    fetch_id: UUID,
    source_key: str,
    digest: str,
) -> None:
    async with sessions() as session, session.begin():
        await session.execute(
            text(
                """
                INSERT INTO ai_dataset_source (
                    id, source_key, source_revision, origin_uri, status,
                    owner_ref, classification, proposed_uses, approved_uses,
                    rights_evidence_ref, rights_evidence_sha256, terms_sha256,
                    row_version
                ) VALUES (
                    :id, :source_key, 'revision-1',
                    'urn:vfbiz:dataset:release-guard', 'purpose-approved',
                    'human:data-owner', 'internal',
                    '["classifier-training"]'::jsonb,
                    '["classifier-training"]'::jsonb,
                    'approval://rights/release-guard', :rights_digest,
                    :terms_digest, 3
                )
                """
            ),
            {
                "id": source_id,
                "source_key": source_key,
                "rights_digest": "a" * 64,
                "terms_digest": "b" * 64,
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO ai_dataset_fetch (
                    id, source_id, state, requested_by,
                    approval_evidence_ref, approval_evidence_sha256,
                    observed_sha256, byte_size, quarantine_uri, scan_evidence,
                    row_version
                ) VALUES (
                    :id, :source_id, 'scan-passed',
                    'dataset-source-researcher',
                    'approval://fetch/release-guard', :approval_digest,
                    :digest, 42, :quarantine_uri,
                    jsonb_build_object(
                        'evidence_ref', 'scan://release-guard/1',
                        'evidence_sha256', CAST(:scan_digest AS text),
                        'artifact_sha256', CAST(:scan_artifact_digest AS text),
                        'scanner_revision', 'vivi-dataset-inspection-v1',
                        'signature_revision', 'clamav-daily-28075',
                        'structural_valid', true,
                        'malware_passed', true,
                        'dlp_decision', 'passed'
                    ),
                    5
                )
                """
            ),
            {
                "id": fetch_id,
                "source_id": source_id,
                "approval_digest": "c" * 64,
                "digest": digest,
                "quarantine_uri": f"file:///quarantine/{digest}",
                "scan_digest": "d" * 64,
                "scan_artifact_digest": digest,
            },
        )


async def insert_release(
    sessions: async_sessionmaker[AsyncSession],
    *,
    release_id: UUID,
    manifest_ref: str,
    source_key: str,
    source_digest: str,
    manifest_digest: str,
    serializable: bool = True,
    purpose: str = "classifier-training",
) -> None:
    async with sessions() as session, session.begin():
        if serializable:
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            )
        await session.execute(
            text(
                """
                INSERT INTO ai_dataset_release (
                    id, manifest_ref, owner_ref, purpose, provenance,
                    classification, approved, manifest_sha256, status,
                    allowed_uses, artifact_ids, row_version
                ) VALUES (
                    :id, :manifest_ref, 'human:data-owner',
                    CAST(:purpose AS text),
                    jsonb_build_object(
                        'sources',
                        jsonb_build_array(
                            jsonb_build_object(
                                'source_id', CAST(:source_key AS text),
                                'source_revision', 'revision-1',
                                'artifact_digest',
                                'sha256:' || CAST(:provenance_digest AS text)
                            )
                        ),
                        'transformation_recipe_revision', 'router-v1',
                        'transformation_recipe_digest',
                        'sha256:' || CAST(:recipe_digest AS text),
                        'lineage_digest',
                        'sha256:' || CAST(:lineage_digest AS text)
                    ),
                    'internal', true, :manifest_digest, 'released',
                    jsonb_build_array(CAST(:purpose AS text)),
                    '[]'::jsonb, 1
                )
                """
            ),
            {
                "id": release_id,
                "manifest_ref": manifest_ref,
                "source_key": source_key,
                "provenance_digest": source_digest,
                "recipe_digest": "e" * 64,
                "lineage_digest": "f" * 64,
                "manifest_digest": manifest_digest,
                "purpose": purpose,
            },
        )


@pytest.mark.asyncio
async def test_dataset_release_provenance_is_atomic_and_non_bypassable() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    source_id = uuid4()
    fetch_id = uuid4()
    fabricated_source_id = uuid4()
    fabricated_fetch_id = uuid4()
    arbitrary_source_id = uuid4()
    arbitrary_fetch_id = uuid4()
    release_id = uuid4()
    read_committed_release_id = uuid4()
    invalid_release_id = uuid4()
    fabricated_release_id = uuid4()
    arbitrary_release_id = uuid4()
    source_key = f"integration-release-guard-{uuid4()}"
    fabricated_source_key = f"integration-release-guard-{uuid4()}"
    arbitrary_source_key = f"integration-release-guard-{uuid4()}"
    environment = f"it-{uuid4().hex[:20]}"
    digest = "9" * 64
    manifest_digest = uuid4().hex + uuid4().hex
    try:
        await seed_source_and_fetch(
            sessions,
            source_id=source_id,
            fetch_id=fetch_id,
            source_key=source_key,
            digest=digest,
        )
        await seed_source_and_fetch(
            sessions,
            source_id=arbitrary_source_id,
            fetch_id=arbitrary_fetch_id,
            source_key=arbitrary_source_key,
            digest=digest,
        )
        async with sessions() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            )
            await session.execute(
                text(
                    """
                    UPDATE ai_dataset_source
                    SET proposed_uses = '{"arbitrary-use": true}'::jsonb,
                        approved_uses = '{"arbitrary-use": false}'::jsonb,
                        row_version = row_version + 1
                    WHERE id = :source_id
                    """
                ),
                {"source_id": arbitrary_source_id},
            )
        with pytest.raises(
            DBAPIError,
            match="one canonical use",
        ):
            await insert_release(
                sessions,
                release_id=arbitrary_release_id,
                manifest_ref=f"dataset://{arbitrary_source_key}/arbitrary",
                source_key=arbitrary_source_key,
                source_digest=digest,
                manifest_digest=uuid4().hex + uuid4().hex,
                purpose="arbitrary-use",
            )
        await seed_source_and_fetch(
            sessions,
            source_id=fabricated_source_id,
            fetch_id=fabricated_fetch_id,
            source_key=fabricated_source_key,
            digest=digest,
        )
        async with sessions() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            )
            await session.execute(
                text(
                    """
                    UPDATE ai_dataset_source
                    SET rights_evidence_ref = NULL,
                        rights_evidence_sha256 = NULL,
                        terms_sha256 = NULL,
                        row_version = row_version + 1
                    WHERE id = :source_id
                    """
                ),
                {"source_id": fabricated_source_id},
            )
        with pytest.raises(
            DBAPIError,
            match="source is not purpose-approved",
        ):
            await insert_release(
                sessions,
                release_id=fabricated_release_id,
                manifest_ref=f"dataset://{fabricated_source_key}/fabricated",
                source_key=fabricated_source_key,
                source_digest=digest,
                manifest_digest=uuid4().hex + uuid4().hex,
            )
        with pytest.raises(DBAPIError, match="serializable"):
            await insert_release(
                sessions,
                release_id=read_committed_release_id,
                manifest_ref=f"dataset://{source_key}/read-committed",
                source_key=source_key,
                source_digest=digest,
                manifest_digest="4" * 64,
                serializable=False,
            )

        await insert_release(
            sessions,
            release_id=release_id,
            manifest_ref=f"dataset://{source_key}/1",
            source_key=source_key,
            source_digest=digest,
            manifest_digest=manifest_digest,
        )

        with pytest.raises(DBAPIError, match="dataset release provenance"):
            await insert_release(
                sessions,
                release_id=invalid_release_id,
                manifest_ref=f"dataset://{source_key}/invalid",
                source_key=source_key,
                source_digest="8" * 64,
                manifest_digest="6" * 64,
            )

        async with sessions() as session:
            with pytest.raises(DBAPIError, match="dependent dataset release"):
                async with session.begin():
                    await session.execute(
                        text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                    )
                    await session.execute(
                        text(
                            """
                            UPDATE ai_dataset_source
                            SET status = 'tombstoned', row_version = row_version + 1
                            WHERE id = :source_id
                            """
                        ),
                        {"source_id": source_id},
                    )

        async with sessions() as session:
            with pytest.raises(DBAPIError, match="dependent dataset release"):
                async with session.begin():
                    await session.execute(
                        text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                    )
                    await session.execute(
                        text(
                            """
                            UPDATE ai_dataset_source
                            SET rights_evidence_sha256 = :replacement_digest,
                                row_version = row_version + 1
                            WHERE id = :source_id
                            """
                        ),
                        {
                            "source_id": source_id,
                            "replacement_digest": "1" * 64,
                        },
                    )

        async with sessions() as session:
            with pytest.raises(DBAPIError, match="dependent dataset release"):
                async with session.begin():
                    await session.execute(
                        text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                    )
                    await session.execute(
                        text(
                            """
                            UPDATE ai_dataset_source
                            SET origin_uri = 'urn:vfbiz:tampered-origin',
                                row_version = row_version + 1
                            WHERE id = :source_id
                            """
                        ),
                        {"source_id": source_id},
                    )

        async with sessions() as session:
            with pytest.raises(DBAPIError, match="dependent dataset release"):
                async with session.begin():
                    await session.execute(
                        text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                    )
                    await session.execute(
                        text("DELETE FROM ai_dataset_fetch WHERE id = :fetch_id"),
                        {"fetch_id": fetch_id},
                    )

        async with sessions() as session:
            with pytest.raises(DBAPIError, match="dependent dataset release"):
                async with session.begin():
                    await session.execute(
                        text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                    )
                    await session.execute(
                        text(
                            """
                            UPDATE ai_dataset_fetch
                            SET approval_evidence_sha256 = :replacement_digest,
                                row_version = row_version + 1
                            WHERE id = :fetch_id
                            """
                        ),
                        {
                            "fetch_id": fetch_id,
                            "replacement_digest": "2" * 64,
                        },
                    )

        async with sessions() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            )
            await session.execute(
                text(
                    """
                    INSERT INTO ai_dataset_release_pointer (
                        environment, purpose, release_id, manifest_sha256,
                        pointer_revision, activated_by
                        ) VALUES (
                        :environment, 'classifier-training', :release_id,
                        :manifest_digest, 1, 'human:release-owner'
                    )
                    """
                ),
                {
                    "environment": environment,
                    "release_id": release_id,
                    "manifest_digest": manifest_digest,
                },
            )

        async with sessions() as session:
            with pytest.raises(
                DBAPIError,
                match="active dataset release pointer must move",
            ):
                async with session.begin():
                    await session.execute(
                        text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                    )
                    await session.execute(
                        text(
                            """
                            UPDATE ai_dataset_release
                            SET status = 'rolled-back',
                                row_version = row_version + 1
                            WHERE id = :release_id
                            """
                        ),
                        {"release_id": release_id},
                    )

        async with sessions() as session:
            with pytest.raises(
                DBAPIError,
                match="active dataset release pointer must move",
            ):
                async with session.begin():
                    await session.execute(
                        text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                    )
                    await session.execute(
                        text(
                            """
                            UPDATE ai_dataset_release
                            SET provenance = jsonb_set(
                                    provenance,
                                    '{lineage_digest}',
                                    to_jsonb(CAST(:replacement AS text))
                                ),
                                row_version = row_version + 1
                            WHERE id = :release_id
                            """
                        ),
                        {
                            "release_id": release_id,
                            "replacement": "sha256:" + ("0" * 64),
                        },
                    )

        async with sessions() as session:
            with pytest.raises(DBAPIError, match="dataset release pointer"):
                async with session.begin():
                    await session.execute(
                        text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                    )
                    await session.execute(
                        text(
                            """
                            UPDATE ai_dataset_release_pointer
                            SET manifest_sha256 = :wrong_digest,
                                pointer_revision = pointer_revision + 1
                            WHERE environment = :environment
                              AND purpose = 'classifier-training'
                            """
                        ),
                        {
                            "environment": environment,
                            "wrong_digest": "5" * 64,
                        },
                    )
    finally:
        async with sessions() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            )
            await session.execute(
                text(
                    """
                    DELETE FROM ai_dataset_release_pointer
                    WHERE release_id IN (
                        :release_id, :invalid_release_id,
                        :read_committed_release_id, :fabricated_release_id,
                        :arbitrary_release_id
                    )
                    """
                ),
                {
                    "release_id": release_id,
                    "invalid_release_id": invalid_release_id,
                    "read_committed_release_id": read_committed_release_id,
                    "fabricated_release_id": fabricated_release_id,
                    "arbitrary_release_id": arbitrary_release_id,
                },
            )
            await session.execute(
                text(
                    """
                    UPDATE ai_dataset_release
                    SET status = 'tombstoned', tombstoned_at = clock_timestamp(),
                        row_version = row_version + 1
                    WHERE id IN (
                        :release_id, :invalid_release_id,
                        :read_committed_release_id, :fabricated_release_id,
                        :arbitrary_release_id
                    )
                    """
                ),
                {
                    "release_id": release_id,
                    "invalid_release_id": invalid_release_id,
                    "read_committed_release_id": read_committed_release_id,
                    "fabricated_release_id": fabricated_release_id,
                    "arbitrary_release_id": arbitrary_release_id,
                },
            )
            await session.execute(
                text(
                    """
                    DELETE FROM ai_dataset_release
                    WHERE id IN (
                        :release_id, :invalid_release_id,
                        :read_committed_release_id, :fabricated_release_id,
                        :arbitrary_release_id
                    )
                    """
                ),
                {
                    "release_id": release_id,
                    "invalid_release_id": invalid_release_id,
                    "read_committed_release_id": read_committed_release_id,
                    "fabricated_release_id": fabricated_release_id,
                    "arbitrary_release_id": arbitrary_release_id,
                },
            )
            await session.execute(
                text("DELETE FROM ai_dataset_fetch WHERE id = :fetch_id"),
                {"fetch_id": fetch_id},
            )
            await session.execute(
                text("DELETE FROM ai_dataset_fetch WHERE id = :fetch_id"),
                {"fetch_id": fabricated_fetch_id},
            )
            await session.execute(
                text("DELETE FROM ai_dataset_fetch WHERE id = :fetch_id"),
                {"fetch_id": arbitrary_fetch_id},
            )
            await session.execute(
                text("DELETE FROM ai_dataset_source WHERE id = :source_id"),
                {"source_id": source_id},
            )
            await session.execute(
                text("DELETE FROM ai_dataset_source WHERE id = :source_id"),
                {"source_id": fabricated_source_id},
            )
            await session.execute(
                text("DELETE FROM ai_dataset_source WHERE id = :source_id"),
                {"source_id": arbitrary_source_id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_migration_refuses_governed_downgrade_and_invalid_legacy_rows() -> None:
    settings = Settings()
    assert settings.database_url is not None
    source_id = uuid4()
    fetch_id = uuid4()
    release_id = uuid4()
    source_key = f"integration-release-guard-{uuid4()}"
    manifest_digest = uuid4().hex + uuid4().hex
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    try:
        await seed_source_and_fetch(
            sessions,
            source_id=source_id,
            fetch_id=fetch_id,
            source_key=source_key,
            digest="3" * 64,
        )
        await insert_release(
            sessions,
            release_id=release_id,
            manifest_ref=f"dataset://{source_key}/downgrade",
            source_key=source_key,
            source_digest="3" * 64,
            manifest_digest=manifest_digest,
        )
        await engine.dispose()

        with pytest.raises(DBAPIError, match="cannot downgrade 20260729_0018"):
            await asyncio.to_thread(
                run_alembic,
                "downgrade",
                "20260728_0017",
            )

        engine = create_engine(settings.database_url)
        sessions = create_session_factory(engine)
        async with sessions() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            )
            await session.execute(
                text(
                    """
                    UPDATE ai_dataset_release
                    SET status = 'tombstoned', row_version = row_version + 1
                    WHERE id = :release_id
                    """
                ),
                {"release_id": release_id},
            )
            await session.execute(
                text("DELETE FROM ai_dataset_release WHERE id = :release_id"),
                {"release_id": release_id},
            )
            await session.execute(
                text("DELETE FROM ai_dataset_fetch WHERE id = :fetch_id"),
                {"fetch_id": fetch_id},
            )
            await session.execute(
                text("DELETE FROM ai_dataset_source WHERE id = :source_id"),
                {"source_id": source_id},
            )
        await engine.dispose()
        await asyncio.to_thread(run_alembic, "downgrade", "20260728_0017")

        engine = create_engine(settings.database_url)
        sessions = create_session_factory(engine)
        await seed_source_and_fetch(
            sessions,
            source_id=source_id,
            fetch_id=fetch_id,
            source_key=source_key,
            digest="3" * 64,
        )
        async with sessions() as session, session.begin():
            await session.execute(
                text(
                    """
                    UPDATE ai_dataset_source
                    SET rights_evidence_ref = NULL,
                        rights_evidence_sha256 = NULL,
                        terms_sha256 = NULL,
                        row_version = row_version + 1
                    WHERE id = :source_id
                    """
                ),
                {"source_id": source_id},
            )
        await insert_release(
            sessions,
            release_id=release_id,
            manifest_ref=f"dataset://{source_key}/legacy-invalid",
            source_key=source_key,
            source_digest="3" * 64,
            manifest_digest=manifest_digest,
        )
        await engine.dispose()

        with pytest.raises(DBAPIError, match="source is not purpose-approved"):
            await asyncio.to_thread(run_alembic, "upgrade", "head")

        engine = create_engine(settings.database_url)
        sessions = create_session_factory(engine)
        async with sessions() as session, session.begin():
            await session.execute(
                text("DELETE FROM ai_dataset_release WHERE id = :release_id"),
                {"release_id": release_id},
            )
            await session.execute(
                text("DELETE FROM ai_dataset_fetch WHERE id = :fetch_id"),
                {"fetch_id": fetch_id},
            )
            await session.execute(
                text("DELETE FROM ai_dataset_source WHERE id = :source_id"),
                {"source_id": source_id},
            )
        await engine.dispose()
        await asyncio.to_thread(run_alembic, "upgrade", "head")
    finally:
        await engine.dispose()
