import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from app.modules.governance.application.release_resolver import ArtifactDigestReader
from app.modules.governance.domain.semantic_classifier_binding import (
    SemanticClassifierReleaseBinding,
)


class SemanticClassifierBindingState(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class SemanticClassifierBindingRecord:
    binding: SemanticClassifierReleaseBinding
    state: SemanticClassifierBindingState
    revision: int

    def __post_init__(self) -> None:
        if self.revision <= 0:
            raise ValueError("semantic classifier binding revision must be positive")


class SemanticClassifierBindingStore(Protocol):
    async def get(
        self,
        *,
        activation_id: str,
        activation_envelope_sha256: str,
    ) -> SemanticClassifierBindingRecord | None: ...


class SemanticClassifierEvidenceVerifier(Protocol):
    async def verify_evaluation(
        self,
        binding: SemanticClassifierReleaseBinding,
    ) -> bool: ...

    async def verify_approval(
        self,
        binding: SemanticClassifierReleaseBinding,
    ) -> bool: ...


class SemanticClassifierFreshnessFence(Protocol):
    def begin_freshness_scope(self) -> object: ...

    async def assert_fresh(self) -> None: ...

    def end_freshness_scope(self, token: object) -> None: ...


class SemanticClassifierBindingResolutionError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SemanticClassifierBindingResolver:
    def __init__(
        self,
        *,
        store: SemanticClassifierBindingStore,
        digest_reader: ArtifactDigestReader,
        evidence_verifier: SemanticClassifierEvidenceVerifier,
        freshness_fence: SemanticClassifierFreshnessFence,
        clock: Callable[[], datetime],
        timeout_seconds: float,
        max_concurrency: int,
    ) -> None:
        if timeout_seconds <= 0 or max_concurrency <= 0:
            raise ValueError("semantic classifier resolver limits must be positive")
        self._store = store
        self._digest_reader = digest_reader
        self._evidence_verifier = evidence_verifier
        self._freshness_fence = freshness_fence
        self._clock = clock
        self._timeout_seconds = timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def resolve(
        self,
        *,
        activation_id: str,
        activation_envelope_sha256: str,
        assistant_profile: str,
        environment: str,
    ) -> SemanticClassifierReleaseBinding:
        acquired = False
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self._semaphore.acquire()
                acquired = True
                return await self._resolve(
                    activation_id=activation_id,
                    activation_envelope_sha256=activation_envelope_sha256,
                    assistant_profile=assistant_profile,
                    environment=environment,
                )
        except TimeoutError as error:
            raise SemanticClassifierBindingResolutionError(
                "CLASSIFIER_BINDING_RESOLUTION_TIMEOUT"
            ) from error
        except asyncio.CancelledError:
            raise
        finally:
            if acquired:
                self._semaphore.release()

    async def _resolve(
        self,
        *,
        activation_id: str,
        activation_envelope_sha256: str,
        assistant_profile: str,
        environment: str,
    ) -> SemanticClassifierReleaseBinding:
        token = self._freshness_fence.begin_freshness_scope()
        try:
            record = await self._store.get(
                activation_id=activation_id,
                activation_envelope_sha256=activation_envelope_sha256,
            )
            if record is None:
                raise SemanticClassifierBindingResolutionError("CLASSIFIER_BINDING_NOT_FOUND")
            if record.state is SemanticClassifierBindingState.REVOKED:
                raise SemanticClassifierBindingResolutionError("CLASSIFIER_BINDING_REVOKED")
            if record.state is not SemanticClassifierBindingState.ACTIVE:
                raise SemanticClassifierBindingResolutionError("CLASSIFIER_BINDING_NOT_ACTIVE")
            binding = record.binding
            if (
                binding.target_activation_id != activation_id
                or binding.target_activation_envelope_sha256 != activation_envelope_sha256
            ):
                raise SemanticClassifierBindingResolutionError("CLASSIFIER_ACTIVATION_MISMATCH")
            if binding.assistant_profile != assistant_profile:
                raise SemanticClassifierBindingResolutionError("CLASSIFIER_PROFILE_MISMATCH")
            if binding.environment != environment:
                raise SemanticClassifierBindingResolutionError("CLASSIFIER_ENVIRONMENT_MISMATCH")
            now = self._clock()
            if now < binding.effective_at:
                raise SemanticClassifierBindingResolutionError("CLASSIFIER_BINDING_NOT_EFFECTIVE")
            if now >= binding.expires_at or now >= binding.evaluation_valid_until:
                raise SemanticClassifierBindingResolutionError("CLASSIFIER_BINDING_EXPIRED")
            for reference, expected_sha256 in binding.artifact_digests():
                if await self._digest_reader.sha256(reference) != expected_sha256:
                    raise SemanticClassifierBindingResolutionError(
                        "CLASSIFIER_ARTIFACT_DIGEST_MISMATCH"
                    )
            if not await self._evidence_verifier.verify_evaluation(binding):
                raise SemanticClassifierBindingResolutionError("CLASSIFIER_EVALUATION_INVALID")
            if not await self._evidence_verifier.verify_approval(binding):
                raise SemanticClassifierBindingResolutionError("CLASSIFIER_APPROVAL_INVALID")
            await self._freshness_fence.assert_fresh()
            return binding
        finally:
            self._freshness_fence.end_freshness_scope(token)
