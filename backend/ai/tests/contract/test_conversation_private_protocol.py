import json
import os
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jsonschema import Draft202012Validator, FormatChecker
from jwt.exceptions import PyJWKClientError
from sqlalchemy import text

from app.bootstrap.conversation_graph import (
    build_conversation_runtime_dependencies,
)
from app.platform.cancellation import (
    CancellationCommand,
    DurableCancellationReceipt,
    PostgresExecutionCancellationAdapter,
)
from app.platform.checkpoints import (
    ActiveTaskCheckpoint,
    CheckpointControlBinding,
    CheckpointEntityReference,
    CheckpointEnvelope,
    CheckpointIdentity,
    CheckpointState,
    assert_checkpoint_control,
)
from app.platform.checkpoints.execution_fence import PostgresExecutionFenceStore
from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory
from app.platform.security.execution_assertion import (
    AllowedPublicKeys,
    canonical_request_hash,
)
from tests.contract.conversation_protocol_fixtures import (
    application_client,
    assertion_claims,
    sign,
    turn_body,
)

ROOT = Path(__file__).resolve().parents[4]


class FailingSigningKeyResolver:
    async def resolve(self, _token: str) -> AllowedPublicKeys:
        raise TimeoutError("JWKS timed out")


class UnknownSigningKeyResolver:
    async def resolve(self, _token: str) -> AllowedPublicKeys:
        raise PyJWKClientError("Unable to find a signing key that matches")


class RecordingCancellationPort:
    def __init__(self) -> None:
        self.commands: list[CancellationCommand] = []

    async def accept_durably(
        self,
        command: CancellationCommand,
    ) -> DurableCancellationReceipt:
        self.commands.append(command)
        return DurableCancellationReceipt(
            cancellation_id=uuid4(),
            request_id=command.request_id,
            turn_id=command.turn_id,
            fencing_token=command.fencing_token,
            persisted_at=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_valid_assertion_reaches_graph_boundary_and_replay_is_rejected() -> None:
    body = turn_body()
    token = sign(assertion_claims(body=body))
    headers = {"X-VFBiz-AI-Assertion": token}

    async with application_client() as http:
        first = await http.post("/internal/v1/conversation/turns", json=body, headers=headers)
        replay = await http.post("/internal/v1/conversation/turns", json=body, headers=headers)

    assert first.status_code == 503
    assert first.json()["code"] == "INTERNAL_FAILURE"
    assert replay.status_code == 401
    assert replay.json()["code"] == "ASSERTION_REPLAYED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claim_override", "expected_status"),
    [
        ({"assistant_profile": "employee"}, 401),
        ({"audience": "wrong-audience"}, 401),
        ({"max_model_tokens": 32_001}, 401),
        ({"action": "turn.cancel"}, 403),
    ],
)
async def test_invalid_profile_audience_budget_or_action_is_rejected(
    claim_override: Mapping[str, object],
    expected_status: int,
) -> None:
    body = turn_body()
    claims = assertion_claims(body=body, **claim_override)

    async with application_client() as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            json=body,
            headers={"X-VFBiz-AI-Assertion": sign(claims)},
        )

    assert response.status_code == expected_status
    assert response.json()["code"] in {"ASSERTION_INVALID", "ASSERTION_MISMATCH"}


@pytest.mark.asyncio
async def test_public_profile_cannot_authorize_customer_scoped_tool() -> None:
    body = turn_body()
    claims = assertion_claims(
        body=body,
        authorization={
            "kind": "public_capability",
            "capabilityHash": "a" * 64,
            "allowedTools": ["get_customer_garage"],
        },
    )

    async with application_client() as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            json=body,
            headers={"X-VFBiz-AI-Assertion": sign(claims)},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "ASSERTION_INVALID"


@pytest.mark.asyncio
async def test_expired_assertion_is_rejected() -> None:
    body = turn_body()
    now = int(time.time()) - 120
    claims = assertion_claims(body=body, issued_at=now, expires_at=now + 60)

    async with application_client() as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            json=body,
            headers={"X-VFBiz-AI-Assertion": sign(claims)},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "ASSERTION_INVALID"


@pytest.mark.asyncio
async def test_jwks_outage_fails_closed_with_retryable_503() -> None:
    body = turn_body()
    token = sign(assertion_claims(body=body))

    async with application_client(key_resolver=FailingSigningKeyResolver()) as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            json=body,
            headers={"X-VFBiz-AI-Assertion": token},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "ASSERTION_INVALID"
    assert response.json()["retryable"] is True


@pytest.mark.asyncio
async def test_unknown_signing_key_is_non_retryable_401() -> None:
    body = turn_body()
    token = sign(assertion_claims(body=body))

    async with application_client(key_resolver=UnknownSigningKeyResolver()) as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            json=body,
            headers={"X-VFBiz-AI-Assertion": token},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "ASSERTION_INVALID"
    assert response.json()["retryable"] is False


@pytest.mark.asyncio
async def test_version_or_fencing_mismatch_is_rejected_after_signature_validation() -> None:
    body = turn_body(conversation_version=2, fencing_token=8)
    claims = assertion_claims(body=body, conversation_version=1, fencing_token=7)

    async with application_client() as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            json=body,
            headers={"X-VFBiz-AI-Assertion": sign(claims)},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "ASSERTION_MISMATCH"


@pytest.mark.asyncio
async def test_locale_mismatch_is_rejected_after_signature_validation() -> None:
    body = turn_body()
    claims = assertion_claims(body=body)
    body["locale"] = "en"
    canonical_body = json.dumps(
        body, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    claims["requestHash"] = canonical_request_hash(
        method="POST",
        path="/internal/v1/conversation/turns",
        body=canonical_body,
    )

    async with application_client() as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            json=body,
            headers={"X-VFBiz-AI-Assertion": sign(claims)},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "ASSERTION_MISMATCH"


@pytest.mark.asyncio
async def test_valid_cancel_assertion_is_accepted() -> None:
    turn = turn_body(conversation_version=2, fencing_token=8)
    body = {
        "requestId": str(uuid4()),
        "conversationVersion": 2,
        "fencingToken": 8,
        "reason": "user_interrupt",
    }
    path = f"/internal/v1/conversation/turns/{turn['turnId']}/cancel"
    claims = assertion_claims(
        body={
            **body,
            "correlationId": turn["correlationId"],
            "sessionId": turn["sessionId"],
            "turnId": turn["turnId"],
        },
        path=path,
        action="turn.cancel",
    )
    canonical_body = json.dumps(
        body, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    claims["requestHash"] = canonical_request_hash(method="POST", path=path, body=canonical_body)

    cancellation_port = RecordingCancellationPort()
    async with application_client(cancellation_port) as http:
        response = await http.post(
            path,
            json=body,
            headers={"X-VFBiz-AI-Assertion": sign(claims)},
        )

    assert response.status_code == 202
    assert str(cancellation_port.commands[0].turn_id) == turn["turnId"]


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)
async def test_real_postgres_cancellation_adapter_accepts_a_valid_cancel_end_to_end() -> None:
    # Proves the production adapter is a drop-in replacement for
    # RecordingCancellationPort through the exact same signed HTTP path,
    # not just in isolated unit tests.
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    async with sessions() as session, session.begin():
        await session.execute(text("TRUNCATE TABLE ai_conversation_execution_fence"))
    cancellation_port = PostgresExecutionCancellationAdapter(
        PostgresExecutionFenceStore(sessions)
    )

    turn = turn_body(conversation_version=2, fencing_token=8)
    body = {
        "requestId": str(uuid4()),
        "conversationVersion": 2,
        "fencingToken": 8,
        "reason": "user_interrupt",
    }
    path = f"/internal/v1/conversation/turns/{turn['turnId']}/cancel"
    claims = assertion_claims(
        body={
            **body,
            "correlationId": turn["correlationId"],
            "sessionId": turn["sessionId"],
            "turnId": turn["turnId"],
        },
        path=path,
        action="turn.cancel",
    )
    canonical_body = json.dumps(
        body, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    claims["requestHash"] = canonical_request_hash(method="POST", path=path, body=canonical_body)

    async with application_client(cancellation_port) as http:
        response = await http.post(
            path,
            json=body,
            headers={"X-VFBiz-AI-Assertion": sign(claims)},
        )

    assert response.status_code == 202
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)
async def test_real_conversation_graph_rejects_turn_without_release_authority() -> None:
    # Missing release authority is an infrastructure failure, not an AI
    # recommendation. NestJS remains the only authority that may create a
    # durable customer-support handoff.
    settings = Settings()
    assert settings.database_url is not None
    assert settings.generation_provider == "disabled"
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    dependencies = await build_conversation_runtime_dependencies(settings, sessions)

    body = turn_body()
    claims = assertion_claims(body=body)

    try:
        async with application_client(conversation_dependencies=dependencies) as http:
            response = await http.post(
                "/internal/v1/conversation/turns",
                json=body,
                headers={"X-VFBiz-AI-Assertion": sign(claims)},
            )
    finally:
        await dependencies.close()
        await engine.dispose()

    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "RELEASE_UNAVAILABLE"
    assert payload["retryable"] is True
    assert payload["detail"] == (
        "The approved assistant runtime is temporarily unavailable."
    )


@pytest.mark.asyncio
async def test_cancel_fails_closed_without_cancellation_boundary() -> None:
    turn = turn_body()
    body = {
        "requestId": str(uuid4()),
        "conversationVersion": 1,
        "fencingToken": 7,
        "reason": "user_interrupt",
    }
    path = f"/internal/v1/conversation/turns/{turn['turnId']}/cancel"
    claims = assertion_claims(
        body={
            **body,
            "correlationId": turn["correlationId"],
            "sessionId": turn["sessionId"],
            "turnId": turn["turnId"],
        },
        path=path,
        action="turn.cancel",
    )
    canonical_body = json.dumps(
        body, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    claims["requestHash"] = canonical_request_hash(method="POST", path=path, body=canonical_body)

    async with application_client() as http:
        response = await http.post(
            path,
            json=body,
            headers={"X-VFBiz-AI-Assertion": sign(claims)},
        )

    assert response.status_code == 503
    assert response.json()["retryable"] is True


@pytest.mark.asyncio
async def test_duplicate_json_keys_are_rejected_without_reaching_graph() -> None:
    body = turn_body()
    raw_body = (json.dumps(body, ensure_ascii=False)[:-1] + ',"conversationVersion":2}').encode()
    claims = assertion_claims(body=body)

    async with application_client() as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-VFBiz-AI-Assertion": sign(claims),
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "ASSERTION_MISMATCH"


@pytest.mark.asyncio
async def test_oversized_request_is_rejected_before_signature_work() -> None:
    async with application_client() as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            content=b"x" * 65_537,
            headers={"X-VFBiz-AI-Assertion": "a" * 64 + ".b.c"},
        )

    assert response.status_code == 413
    assert response.json()["code"] == "REQUEST_TOO_LARGE"


@pytest.mark.asyncio
async def test_legacy_answer_route_is_not_mounted() -> None:
    async with application_client() as http:
        response = await http.post("/internal/v1/answers", json={})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_internal_problem_response_conforms_to_openapi_schema() -> None:
    body = turn_body()
    token = sign(assertion_claims(body=body, audience="wrong-audience"))

    async with application_client() as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            json=body,
            headers={"X-VFBiz-AI-Assertion": token},
        )

    assert response.headers["content-type"].startswith("application/problem+json")
    problem = response.json()
    assert set(problem) == {
        "type",
        "title",
        "status",
        "detail",
        "instance",
        "code",
        "retryable",
        "correlationId",
    }
    assert problem["status"] == response.status_code
    assert isinstance(problem["retryable"], bool)


def test_claim_fixture_conforms_to_shared_execution_assertion_contract() -> None:
    schema = json.loads((ROOT / "contracts/ai/ai-execution-assertion.schema.json").read_text())
    body = turn_body()
    claims = assertion_claims(body=body)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(claims)


def test_canonical_request_hash_matches_shared_cross_runtime_vectors() -> None:
    fixture = json.loads((ROOT / "contracts/ai/canonical-request-hash-vectors.json").read_text())
    for vector in fixture["vectors"]:
        body = json.dumps(
            vector["body"],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        assert body.decode() == vector["canonicalBody"]
        assert (
            canonical_request_hash(
                method=vector["method"],
                path=vector["path"],
                body=body,
            )
            == vector["sha256"]
        )
    for rejection in fixture["rejections"]:
        if rejection["error"] == "QUERY_PARAMETERS_FORBIDDEN":
            continue
        with pytest.raises(HTTPException):
            canonical_request_hash(
                method=rejection["method"],
                path=rejection["path"],
                body=rejection["rawBody"].encode(),
            )


def test_checkpoint_contract_cannot_become_conversation_history_authority() -> None:
    identity = CheckpointIdentity(
        session_id=uuid4(),
        turn_id=uuid4(),
        graph_version="graph-r1",
    )
    checkpoint = CheckpointEnvelope(
        schema_version=1,
        identity=identity,
        conversation_version=1,
        fencing_token=7,
        control=CheckpointControlBinding(
            assistant_profile="public_customer",
            authorization_context_hash="a" * 64,
            policy_revision="policy-r1",
            knowledge_revision="knowledge-r1",
        ),
        state=CheckpointState(
            active_task=ActiveTaskCheckpoint(
                task_kind="knowledge_question",
                stage="accepted",
                retry_count=0,
            )
        ),
        created_at="2026-07-25T00:00:00Z",
    )

    assert checkpoint.authority == "ai_execution_only"
    assert {"transcript", "final_answer", "customer_profile"}.isdisjoint(
        CheckpointEnvelope.model_fields
    )
    with pytest.raises(ValueError, match="control binding"):
        assert_checkpoint_control(
            checkpoint,
            CheckpointControlBinding(
                assistant_profile="public_customer",
                authorization_context_hash="b" * 64,
                policy_revision="policy-r1",
                knowledge_revision="knowledge-r1",
            ),
        )


def test_checkpoint_rejects_free_form_evidence_or_slot_payload() -> None:
    with pytest.raises(ValueError):
        CheckpointState(evidence_refs=("customer said my VIN is private",))
    with pytest.raises(ValueError):
        ActiveTaskCheckpoint(
            task_kind="knowledge_question",
            stage="accepted",
            retry_count=0,
            pending_slot_names=("raw customer transcript",),
        )
    with pytest.raises(ValueError):
        CheckpointState(
            evidence_refs=("citation:VF8VINRLZ123456789",),
        )
    with pytest.raises(ValueError):
        CheckpointState(
            evidence_refs=("tool:0123456789abcdef.customer-id",),
        )
    with pytest.raises(ValueError):
        CheckpointEntityReference(
            kind="vehicle_model",
            reference="VF8VINRLZ123456789",
            source_revision="catalog-r1",
            classification="non_sensitive",
        )


def test_reviewed_langgraph_dependencies_are_pinned() -> None:
    assert version("langgraph") == "1.2.9"
    assert version("langgraph-checkpoint-postgres") == "3.1.0"
