"""HTTP-boundary mapping for graph outcomes that a real end-to-end run cannot
deterministically produce.

`GRAPH_IDENTITY_MISMATCH`, `TURN_DEADLINE_EXCEEDED` and `STALE_FENCING_TOKEN`
are all proven reachable at the `ConversationGraphRuntime`/graph-node level by
existing unit tests (`tests/unit/assistant/test_graph_runtime.py`,
`tests/unit/assistant/test_graph_execution.py`). What is untested is whether
`execute_turn` maps each of them to the right HTTP response. Driving these
exact outcomes through a real graph run would require either a genuinely
impossible precondition (`execute_turn` always derives `control.graph_version`
and `identity.graph_version` from the same signed claim, so they can never
diverge through this router) or an unreliable wall-clock race (a deadline that
is valid when the assertion is verified but has elapsed a few microseconds
later, inside `runtime.start()`). Both are sidestepped here by monkeypatching
`build_turn_runtime` with a fake whose `start()` returns a fixed outcome,
isolating exactly the thing this file is testing: the router's own mapping.
"""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast

import pytest

from app.bootstrap.conversation_graph import ConversationRuntimeDependencies
from app.modules.assistant.domain import GraphOutcome
from app.modules.assistant.graph.runtime import ResumeRejected
from tests.contract.conversation_protocol_fixtures import (
    application_client,
    assertion_claims,
    sign,
    turn_body,
)


class _FakeTurnRuntime:
    def __init__(self, outcome: object, *, release_changed: bool = False) -> None:
        self._outcome = outcome
        self._release_changed = release_changed
        self.release = SimpleNamespace(
            activation_id="00000000-0000-4000-8000-000000000010",
            candidate_sha256="a" * 64,
            activation_envelope_sha256="b" * 64,
            pointer_revision=1,
        )

    async def start(self, _state: object, *, identity: object) -> dict[str, object]:
        return {
            "cost_microusd": 250,
            "model_tokens": 75,
            "outcome": self._outcome,
        }

    async def assert_release_current(self) -> None:
        if self._release_changed:
            from app.bootstrap.release_runtime import ReleaseRuntimeUnavailable

            raise ReleaseRuntimeUnavailable("RELEASE_CHANGED_DURING_TURN")
        return None

    async def issue_commit_lease(self, **_kwargs: object) -> object:
        issued_at = datetime.now(UTC)
        return SimpleNamespace(
            lease_id="00000000-0000-4000-8000-000000000001",
            issued_at=issued_at,
            expires_at=issued_at + timedelta(seconds=15),
        )

    async def close(self) -> None:
        return None


def _client_with_fixed_outcome(
    monkeypatch: pytest.MonkeyPatch,
    outcome: object,
    *,
    release_changed: bool = False,
) -> Mapping[str, object]:
    # Imported here, not at module level: app.api.internal_v1.conversation_router
    # and app.bootstrap.application import from each other (the router needs
    # build_turn_runtime, application.py registers internal_v1_router). If this
    # module ever became the first thing in the process to touch
    # app.api.internal_v1 — e.g. run in isolation, before the
    # conversation_protocol_fixtures import above has pulled in app.main and
    # settled that cycle from the app.bootstrap side — a module-level import
    # here would fail with "cannot import name 'internal_v1_router' from
    # partially initialized module app.api.internal_v1". Deferring it to call
    # time, after collection has already imported app.main, sidesteps that
    # regardless of module import order.
    from app.api.internal_v1 import conversation_router

    async def fake_build_turn_runtime(*_args: object, **_kwargs: object) -> _FakeTurnRuntime:
        return _FakeTurnRuntime(outcome, release_changed=release_changed)

    monkeypatch.setattr(conversation_router, "build_turn_runtime", fake_build_turn_runtime)
    body = turn_body()
    claims = assertion_claims(body=body)
    return {"body": body, "headers": {"X-VFBiz-AI-Assertion": sign(claims)}}


@pytest.mark.asyncio
async def test_release_change_suppresses_answer_but_preserves_incurred_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _client_with_fixed_outcome(
        monkeypatch,
        GraphOutcome(kind="completed", code="ANSWERED"),
        release_changed=True,
    )

    async with application_client(
        conversation_dependencies=cast(ConversationRuntimeDependencies, object())
    ) as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            json=request["body"],
            headers=cast(dict[str, str], request["headers"]),
        )

    assert response.status_code == 200
    assert response.json() == {
        "outcome": "failed_safely",
        "code": "RELEASE_SUPPRESSED",
        "message": (
            "Xin lỗi, hiện tại tôi chưa thể trả lời câu hỏi này. "
            "Vui lòng liên hệ tổng đài hỗ trợ VinFast."
        ),
        "releaseRevision": "00000000-0000-4000-8000-000000000010",
        "revisions": {
            "graph": "graph-r1",
            "knowledge": "knowledge-active-r1",
            "policy": "policy-r1",
        },
        "usage": {"costMicros": 250, "modelTokens": 75},
    }


@pytest.mark.asyncio
async def test_graph_identity_mismatch_fails_closed_as_a_retryable_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _client_with_fixed_outcome(
        monkeypatch, ResumeRejected(code="GRAPH_IDENTITY_MISMATCH")
    )

    async with application_client(
        conversation_dependencies=cast(ConversationRuntimeDependencies, object())
    ) as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            json=request["body"],
            headers=cast(dict[str, str], request["headers"]),
        )

    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "INTERNAL_FAILURE"
    assert payload["retryable"] is True
    assert "GRAPH_IDENTITY_MISMATCH" in payload["detail"]


@pytest.mark.asyncio
async def test_turn_deadline_exceeded_at_resume_claim_fails_closed_as_a_retryable_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ResumeRejected(code="TURN_DEADLINE_EXCEEDED") is what runtime.start()
    # returns when the resume-claim reservation itself times out against the
    # deadline (runtime.py's own reserve_start() branch) — before the graph
    # ever runs.
    request = _client_with_fixed_outcome(
        monkeypatch, ResumeRejected(code="TURN_DEADLINE_EXCEEDED")
    )

    async with application_client(
        conversation_dependencies=cast(ConversationRuntimeDependencies, object())
    ) as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            json=request["body"],
            headers=cast(dict[str, str], request["headers"]),
        )

    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "INTERNAL_FAILURE"
    assert payload["retryable"] is True
    assert "TURN_DEADLINE_EXCEEDED" in payload["detail"]


@pytest.mark.asyncio
async def test_turn_deadline_exceeded_mid_execution_fails_closed_as_a_retryable_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The same code can also arrive as a cancelled GraphOutcome from inside
    # the execute node (terminal_control_outcome()/_execute_bounded() in
    # graph/nodes.py) once the graph is already running. The router maps
    # this through a different branch (outcome.kind == "cancelled") than the
    # ResumeRejected case above, so both are worth covering separately.
    request = _client_with_fixed_outcome(
        monkeypatch, GraphOutcome(kind="cancelled", code="TURN_DEADLINE_EXCEEDED")
    )

    async with application_client(
        conversation_dependencies=cast(ConversationRuntimeDependencies, object())
    ) as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            json=request["body"],
            headers=cast(dict[str, str], request["headers"]),
        )

    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "INTERNAL_FAILURE"
    assert payload["retryable"] is True
    assert "TURN_DEADLINE_EXCEEDED" in payload["detail"]


@pytest.mark.asyncio
async def test_stale_fencing_token_fails_closed_as_a_non_retryable_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _client_with_fixed_outcome(
        monkeypatch, GraphOutcome(kind="cancelled", code="STALE_FENCING_TOKEN")
    )

    async with application_client(
        conversation_dependencies=cast(ConversationRuntimeDependencies, object())
    ) as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            json=request["body"],
            headers=cast(dict[str, str], request["headers"]),
        )

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "STALE_FENCING_TOKEN"
    assert payload["retryable"] is False


@pytest.mark.asyncio
async def test_duplicate_turn_start_fails_closed_as_a_non_retryable_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Same 409 family as stale fencing; included here so this file proves
    # every ResumeRejected/cancelled branch execute_turn distinguishes, not
    # just the three named in this file's module docstring.
    request = _client_with_fixed_outcome(
        monkeypatch, ResumeRejected(code="DUPLICATE_TURN_START")
    )

    async with application_client(
        conversation_dependencies=cast(ConversationRuntimeDependencies, object())
    ) as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            json=request["body"],
            headers=cast(dict[str, str], request["headers"]),
        )

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "DUPLICATE_TURN_START"
    assert payload["retryable"] is False


@pytest.mark.asyncio
async def test_unrecognized_cancellation_code_fails_closed_as_a_retryable_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _client_with_fixed_outcome(
        monkeypatch, GraphOutcome(kind="cancelled", code="EXECUTION_CONTROL_TIMEOUT")
    )

    async with application_client(
        conversation_dependencies=cast(ConversationRuntimeDependencies, object())
    ) as http:
        response = await http.post(
            "/internal/v1/conversation/turns",
            json=request["body"],
            headers=cast(dict[str, str], request["headers"]),
        )

    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "INTERNAL_FAILURE"
    assert payload["retryable"] is True
    assert "EXECUTION_CONTROL_TIMEOUT" in payload["detail"]
