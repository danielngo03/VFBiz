import os

import pytest

from app.modules.assistant.graph.serialization import require_strict_checkpointer
from app.platform.checkpoints.graph_checkpointer import (
    create_conversation_checkpointer_runtime,
    psycopg_conninfo,
)
from app.platform.config import Settings

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)


def test_psycopg_conninfo_strips_the_asyncpg_driver_suffix() -> None:
    assert psycopg_conninfo("postgresql+asyncpg://user:pw@host:5432/db") == (
        "postgresql://user:pw@host:5432/db"
    )


def test_psycopg_conninfo_passes_through_a_url_without_the_asyncpg_suffix() -> None:
    assert psycopg_conninfo("postgresql://user:pw@host:5432/db") == (
        "postgresql://user:pw@host:5432/db"
    )


@pytest.mark.asyncio
async def test_creates_a_checkpointer_that_passes_the_strict_allowlist_gate() -> None:
    settings = Settings()
    assert settings.database_url is not None

    runtime = await create_conversation_checkpointer_runtime(settings.database_url)
    try:
        # Must not raise: proves allowed_msgpack_modules/allowed_json_modules
        # are explicitly None, not the permissive default.
        require_strict_checkpointer(runtime.saver)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_checkpointer_round_trips_a_real_graph_turn() -> None:
    from app.modules.assistant.application import WorkerResult
    from app.modules.assistant.graph.builder import build_conversation_graph
    from tests.unit.assistant.conversation_fakes import (
        DeterministicSupervisor,
        EvidenceAuthority,
        ExecutionControl,
        SequenceWorker,
        control,
        initial_state,
    )

    settings = Settings()
    assert settings.database_url is not None
    runtime = await create_conversation_checkpointer_runtime(settings.database_url)
    try:
        graph = build_conversation_graph(
            supervisor=DeterministicSupervisor(),
            worker=SequenceWorker(
                [
                    WorkerResult(
                        kind="completed",
                        code="ANSWERED",
                        fencing_token=7,
                        final_answer="VF 8 có phạm vi hoạt động khoảng 470km.",
                        evidence=(),
                    )
                ]
            ),
            execution_control=ExecutionControl(),
            evidence_authority=EvidenceAuthority(),
            checkpointer=runtime.saver,
        )
        state = initial_state(message="VF 8 đi được bao xa?", graph_control=control())
        result = await graph.ainvoke(
            state, config={"configurable": {"thread_id": "checkpointer-roundtrip-1"}}
        )

        assert result["outcome"].kind == "refused"
        assert result["outcome"].code == "MISSING_GROUNDED_EVIDENCE"
    finally:
        await runtime.close()
