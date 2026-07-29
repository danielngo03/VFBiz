import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.modules.governance.application.semantic_classifier_binding import (
    SemanticClassifierBindingRecord,
    SemanticClassifierBindingResolutionError,
    SemanticClassifierBindingResolver,
    SemanticClassifierBindingState,
)
from app.modules.governance.domain import (
    ReleaseAuthorityContractError,
    SemanticClassifierReleaseBinding,
    canonical_sha256,
)
from app.modules.governance.infrastructure import JsonSchemaAuthorityValidator

NOW = datetime(2026, 7, 29, 9, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[5]
SCHEMA = json.loads(
    (ROOT / "contracts/ai/releases/semantic-classifier-binding.schema.json").read_text(
        encoding="utf-8"
    )
)


def binding_document() -> dict[str, Any]:
    classifier = {
        "ref": "classifier://customer-assistant/semantic-router/v1",
        "sha256": "a" * 64,
        "revision": "semantic-router-v1",
    }
    output_schema = {
        "ref": "schema://customer-assistant/semantic-route/v1",
        "sha256": "b" * 64,
        "revision": "semantic-route-schema-v1",
    }
    routing_policy = {
        "ref": "policy://customer-assistant/semantic-routing/v1",
        "sha256": "c" * 64,
        "revision": "semantic-routing-policy-v1",
        "threshold_authority": "code-owned",
    }
    stack_sha256 = canonical_sha256(
        {
            "classifier_artifact": classifier,
            "output_schema": output_schema,
            "routing_policy": routing_policy,
        }
    )
    evaluation = {
        "ref": "evaluation://customer-assistant/semantic-router/v1",
        "sha256": "d" * 64,
        "suite_revision": "semantic-router-golden-v1",
        "target_classification_stack_sha256": stack_sha256,
        "valid_until": "2026-08-29T00:00:00+00:00",
    }
    target = {
        "activation_id": "activation.customer-assistant.staging.v3",
        "activation_envelope_sha256": "e" * 64,
        "assistant_profile": "customer-assistant",
        "environment": "staging",
    }
    core = {
        "schema_version": 1,
        "binding_id": "classifier-binding.customer-assistant.staging.v1",
        "target_activation": target,
        "classification_stack_sha256": stack_sha256,
        "evaluation_evidence": evaluation,
        "effective_at": "2026-07-29T00:00:00+00:00",
        "expires_at": "2026-08-29T00:00:00+00:00",
    }
    core_sha256 = canonical_sha256(core)
    approval = {
        "ref": "approval://customer-assistant/semantic-router/v1",
        "sha256": "f" * 64,
        "target_binding_core_sha256": core_sha256,
    }
    return {
        "schema_version": 1,
        "binding_id": core["binding_id"],
        "target_activation": target,
        "classifier_artifact": classifier,
        "output_schema": output_schema,
        "routing_policy": routing_policy,
        "classification_stack_sha256": stack_sha256,
        "evaluation_evidence": evaluation,
        "effective_at": core["effective_at"],
        "expires_at": core["expires_at"],
        "binding_core_sha256": core_sha256,
        "approval_evidence": approval,
        "binding_envelope_sha256": canonical_sha256(
            {
                "approval_evidence": approval,
                "binding_core_sha256": core_sha256,
            }
        ),
    }


def parse_binding(
    document: Mapping[str, Any] | None = None,
) -> SemanticClassifierReleaseBinding:
    return SemanticClassifierReleaseBinding(
        document or binding_document(),
        schema_validator=JsonSchemaAuthorityValidator(SCHEMA),
    )


def test_binding_recomputes_every_authority_digest() -> None:
    binding = parse_binding()

    assert binding.target_activation_id == "activation.customer-assistant.staging.v3"
    assert binding.classifier_revision == "semantic-router-v1"
    assert binding.output_schema_revision == "semantic-route-schema-v1"
    assert binding.routing_policy_revision == "semantic-routing-policy-v1"
    assert binding.evaluation_suite_revision == "semantic-router-golden-v1"
    assert binding.artifact_digests() == (
        ("classifier://customer-assistant/semantic-router/v1", "a" * 64),
        ("schema://customer-assistant/semantic-route/v1", "b" * 64),
        ("policy://customer-assistant/semantic-routing/v1", "c" * 64),
    )


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("classification_stack_sha256", "0" * 64, "classification stack digest"),
        ("binding_core_sha256", "1" * 64, "binding core digest"),
        ("binding_envelope_sha256", "2" * 64, "binding envelope digest"),
    ],
)
def test_binding_rejects_caller_supplied_digest_tampering(
    field: str,
    replacement: str,
    message: str,
) -> None:
    document = binding_document()
    document[field] = replacement

    with pytest.raises(ReleaseAuthorityContractError, match=message):
        parse_binding(document)


def test_binding_rejects_mismatched_evaluation_and_approval_targets() -> None:
    document = binding_document()
    document["evaluation_evidence"]["target_classification_stack_sha256"] = "3" * 64
    with pytest.raises(ReleaseAuthorityContractError, match="evaluation target"):
        parse_binding(document)

    document = binding_document()
    document["approval_evidence"]["target_binding_core_sha256"] = "4" * 64
    with pytest.raises(ReleaseAuthorityContractError, match="approval target"):
        parse_binding(document)


def test_binding_applies_the_canonical_schema_before_semantic_checks() -> None:
    document = binding_document()
    document["routing_policy"]["ref"] = "https://attacker.example/policy"

    with pytest.raises(
        ReleaseAuthorityContractError,
        match="schema validation failed",
    ):
        parse_binding(document)


class FixedStore:
    def __init__(
        self,
        record: SemanticClassifierBindingRecord | None,
    ) -> None:
        self.record = record

    async def get(
        self,
        *,
        activation_id: str,
        activation_envelope_sha256: str,
    ) -> SemanticClassifierBindingRecord | None:
        return self.record


class FixedDigestReader:
    def __init__(self, binding: SemanticClassifierReleaseBinding) -> None:
        self.digests = dict(binding.artifact_digests())

    async def sha256(self, artifact_ref: str) -> str | None:
        return self.digests.get(artifact_ref)


class FixedEvidenceVerifier:
    def __init__(
        self,
        *,
        evaluation_valid: bool = True,
        approval_valid: bool = True,
    ) -> None:
        self.evaluation_valid = evaluation_valid
        self.approval_valid = approval_valid

    async def verify_evaluation(
        self,
        binding: SemanticClassifierReleaseBinding,
    ) -> bool:
        del binding
        return self.evaluation_valid

    async def verify_approval(
        self,
        binding: SemanticClassifierReleaseBinding,
    ) -> bool:
        del binding
        return self.approval_valid


class RecordingFreshnessFence:
    def __init__(self) -> None:
        self.events: list[str] = []

    def begin_freshness_scope(self) -> object:
        self.events.append("begin")
        return object()

    async def assert_fresh(self) -> None:
        self.events.append("assert")

    def end_freshness_scope(self, token: object) -> None:
        del token
        self.events.append("end")


def resolver_for(
    binding: SemanticClassifierReleaseBinding | None,
    *,
    clock: datetime = NOW,
    digest_reader: FixedDigestReader | None = None,
    evidence_verifier: FixedEvidenceVerifier | None = None,
) -> tuple[SemanticClassifierBindingResolver, RecordingFreshnessFence]:
    fence = RecordingFreshnessFence()
    parsed = binding or parse_binding()
    record = (
        SemanticClassifierBindingRecord(
            binding=binding,
            state=SemanticClassifierBindingState.ACTIVE,
            revision=1,
        )
        if binding is not None
        else None
    )
    return (
        SemanticClassifierBindingResolver(
            store=FixedStore(record),
            digest_reader=digest_reader or FixedDigestReader(parsed),
            evidence_verifier=evidence_verifier or FixedEvidenceVerifier(),
            freshness_fence=fence,
            clock=lambda: clock,
            timeout_seconds=1,
            max_concurrency=2,
        ),
        fence,
    )


@pytest.mark.asyncio
async def test_manifest_v3_alone_cannot_enable_semantic_routing() -> None:
    resolver, fence = resolver_for(None)

    with pytest.raises(
        SemanticClassifierBindingResolutionError,
        match="CLASSIFIER_BINDING_NOT_FOUND",
    ):
        await resolver.resolve(
            activation_id="activation.customer-assistant.staging.v3",
            activation_envelope_sha256="e" * 64,
            assistant_profile="customer-assistant",
            environment="staging",
        )

    assert fence.events == ["begin", "end"]


@pytest.mark.asyncio
async def test_resolver_binds_activation_artifacts_evidence_and_freshness() -> None:
    binding = parse_binding()
    resolver, fence = resolver_for(binding)

    resolved = await resolver.resolve(
        activation_id=binding.target_activation_id,
        activation_envelope_sha256=binding.target_activation_envelope_sha256,
        assistant_profile="customer-assistant",
        environment="staging",
    )

    assert resolved.binding_envelope_sha256 == binding.binding_envelope_sha256
    assert fence.events == ["begin", "assert", "end"]


@pytest.mark.asyncio
async def test_resolver_rejects_wrong_activation_or_expired_binding() -> None:
    binding = parse_binding()
    resolver, _ = resolver_for(binding)
    with pytest.raises(
        SemanticClassifierBindingResolutionError,
        match="CLASSIFIER_ACTIVATION_MISMATCH",
    ):
        await resolver.resolve(
            activation_id="activation.other.staging.v3",
            activation_envelope_sha256=binding.target_activation_envelope_sha256,
            assistant_profile="customer-assistant",
            environment="staging",
        )

    resolver, _ = resolver_for(binding, clock=NOW + timedelta(days=40))
    with pytest.raises(
        SemanticClassifierBindingResolutionError,
        match="CLASSIFIER_BINDING_EXPIRED",
    ):
        await resolver.resolve(
            activation_id=binding.target_activation_id,
            activation_envelope_sha256=binding.target_activation_envelope_sha256,
            assistant_profile="customer-assistant",
            environment="staging",
        )


@pytest.mark.asyncio
async def test_resolver_distinguishes_revoked_binding_from_missing_binding() -> None:
    binding = parse_binding()
    fence = RecordingFreshnessFence()
    resolver = SemanticClassifierBindingResolver(
        store=FixedStore(
            SemanticClassifierBindingRecord(
                binding=binding,
                state=SemanticClassifierBindingState.REVOKED,
                revision=2,
            )
        ),
        digest_reader=FixedDigestReader(binding),
        evidence_verifier=FixedEvidenceVerifier(),
        freshness_fence=fence,
        clock=lambda: NOW,
        timeout_seconds=1,
        max_concurrency=1,
    )

    with pytest.raises(
        SemanticClassifierBindingResolutionError,
        match="CLASSIFIER_BINDING_REVOKED",
    ):
        await resolver.resolve(
            activation_id=binding.target_activation_id,
            activation_envelope_sha256=binding.target_activation_envelope_sha256,
            assistant_profile="customer-assistant",
            environment="staging",
        )
    assert fence.events == ["begin", "end"]


@pytest.mark.asyncio
async def test_resolver_rejects_untrusted_artifact_and_evidence() -> None:
    binding = parse_binding()
    reader = FixedDigestReader(binding)
    reader.digests["classifier://customer-assistant/semantic-router/v1"] = "0" * 64
    resolver, fence = resolver_for(binding, digest_reader=reader)
    with pytest.raises(
        SemanticClassifierBindingResolutionError,
        match="CLASSIFIER_ARTIFACT_DIGEST_MISMATCH",
    ):
        await resolver.resolve(
            activation_id=binding.target_activation_id,
            activation_envelope_sha256=binding.target_activation_envelope_sha256,
            assistant_profile="customer-assistant",
            environment="staging",
        )
    assert fence.events == ["begin", "end"]

    resolver, fence = resolver_for(
        binding,
        evidence_verifier=FixedEvidenceVerifier(evaluation_valid=False),
    )
    with pytest.raises(
        SemanticClassifierBindingResolutionError,
        match="CLASSIFIER_EVALUATION_INVALID",
    ):
        await resolver.resolve(
            activation_id=binding.target_activation_id,
            activation_envelope_sha256=binding.target_activation_envelope_sha256,
            assistant_profile="customer-assistant",
            environment="staging",
        )
    assert fence.events == ["begin", "end"]


@pytest.mark.asyncio
async def test_resolver_bounds_a_stalled_binding_lookup() -> None:
    binding = parse_binding()

    class SlowStore(FixedStore):
        async def get(
            self,
            *,
            activation_id: str,
            activation_envelope_sha256: str,
        ) -> SemanticClassifierBindingRecord | None:
            del activation_id, activation_envelope_sha256
            await asyncio.sleep(1)
            return self.record

    fence = RecordingFreshnessFence()
    resolver = SemanticClassifierBindingResolver(
        store=SlowStore(
            SemanticClassifierBindingRecord(
                binding=binding,
                state=SemanticClassifierBindingState.ACTIVE,
                revision=1,
            )
        ),
        digest_reader=FixedDigestReader(binding),
        evidence_verifier=FixedEvidenceVerifier(),
        freshness_fence=fence,
        clock=lambda: NOW,
        timeout_seconds=0.01,
        max_concurrency=1,
    )

    with pytest.raises(
        SemanticClassifierBindingResolutionError,
        match="CLASSIFIER_BINDING_RESOLUTION_TIMEOUT",
    ):
        await resolver.resolve(
            activation_id=binding.target_activation_id,
            activation_envelope_sha256=binding.target_activation_envelope_sha256,
            assistant_profile="customer-assistant",
            environment="staging",
        )
    assert fence.events == ["begin", "end"]


@pytest.mark.asyncio
async def test_resolver_enforces_concurrency_and_recovers_permit_after_timeout() -> None:
    binding = parse_binding()

    class CountingStore(FixedStore):
        current = 0
        maximum = 0
        delay = True

        async def get(
            self,
            *,
            activation_id: str,
            activation_envelope_sha256: str,
        ) -> SemanticClassifierBindingRecord | None:
            del activation_id, activation_envelope_sha256
            self.current += 1
            self.maximum = max(self.maximum, self.current)
            try:
                if self.delay:
                    await asyncio.sleep(1)
                return self.record
            finally:
                self.current -= 1

    store = CountingStore(
        SemanticClassifierBindingRecord(
            binding=binding,
            state=SemanticClassifierBindingState.ACTIVE,
            revision=1,
        )
    )
    resolver = SemanticClassifierBindingResolver(
        store=store,
        digest_reader=FixedDigestReader(binding),
        evidence_verifier=FixedEvidenceVerifier(),
        freshness_fence=RecordingFreshnessFence(),
        clock=lambda: NOW,
        timeout_seconds=0.02,
        max_concurrency=1,
    )
    results = await asyncio.gather(
        resolver.resolve(
            activation_id=binding.target_activation_id,
            activation_envelope_sha256=binding.target_activation_envelope_sha256,
            assistant_profile="customer-assistant",
            environment="staging",
        ),
        resolver.resolve(
            activation_id=binding.target_activation_id,
            activation_envelope_sha256=binding.target_activation_envelope_sha256,
            assistant_profile="customer-assistant",
            environment="staging",
        ),
        return_exceptions=True,
    )

    assert store.maximum == 1
    assert all(
        isinstance(result, SemanticClassifierBindingResolutionError)
        and result.code == "CLASSIFIER_BINDING_RESOLUTION_TIMEOUT"
        for result in results
    )

    store.record = None
    store.delay = False
    with pytest.raises(
        SemanticClassifierBindingResolutionError,
        match="CLASSIFIER_BINDING_NOT_FOUND",
    ):
        await resolver.resolve(
            activation_id=binding.target_activation_id,
            activation_envelope_sha256=binding.target_activation_envelope_sha256,
            assistant_profile="customer-assistant",
            environment="staging",
        )


@pytest.mark.asyncio
async def test_resolver_propagates_cancellation() -> None:
    binding = parse_binding()

    class BlockingStore(FixedStore):
        async def get(
            self,
            *,
            activation_id: str,
            activation_envelope_sha256: str,
        ) -> SemanticClassifierBindingRecord | None:
            await asyncio.Future()
            return None

    fence = RecordingFreshnessFence()
    resolver = SemanticClassifierBindingResolver(
        store=BlockingStore(
            SemanticClassifierBindingRecord(
                binding=binding,
                state=SemanticClassifierBindingState.ACTIVE,
                revision=1,
            )
        ),
        digest_reader=FixedDigestReader(binding),
        evidence_verifier=FixedEvidenceVerifier(),
        freshness_fence=fence,
        clock=lambda: NOW,
        timeout_seconds=60,
        max_concurrency=1,
    )
    task = asyncio.create_task(
        resolver.resolve(
            activation_id=binding.target_activation_id,
            activation_envelope_sha256=binding.target_activation_envelope_sha256,
            assistant_profile="customer-assistant",
            environment="staging",
        )
    )
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert fence.events == ["begin", "end"]
