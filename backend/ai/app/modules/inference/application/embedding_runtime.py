from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import uuid4

from app.modules.inference.application.embedding_ports import (
    CancellationSignal,
    EmbeddingBudget,
    EmbeddingGenerationIdentity,
    EmbeddingInput,
    EmbeddingProvider,
    EmbeddingPurpose,
    EmbeddingRequest,
)


class TokenEstimator(Protocol):
    def estimate(self, text: str) -> int: ...


class ConservativeByteTokenEstimator:
    """Fail-safe upper bound until a release-pinned tokenizer is composed."""

    def estimate(self, text: str) -> int:
        return max(1, len(text.encode("utf-8")))


@dataclass(frozen=True, slots=True)
class EmbeddingRuntimePolicy:
    generation: EmbeddingGenerationIdentity
    timeout_seconds: float
    max_items: int
    max_input_bytes: int
    max_input_tokens: int
    max_cost_microusd: int

    def __post_init__(self) -> None:
        if (
            min(
                self.generation.dimension,
                self.timeout_seconds,
                self.max_items,
                self.max_input_bytes,
                self.max_input_tokens,
                self.max_cost_microusd,
            )
            <= 0
        ):
            raise ValueError("embedding runtime limits must be positive")


class EmbeddingRuntime:
    def __init__(
        self,
        *,
        provider: EmbeddingProvider,
        token_estimator: TokenEstimator,
        policy: EmbeddingRuntimePolicy,
        clock: Callable[[], datetime],
    ) -> None:
        self._provider = provider
        self._token_estimator = token_estimator
        self._policy = policy
        self._clock = clock

    @property
    def revision(self) -> str:
        return self._policy.generation.digest

    @property
    def dimension(self) -> int:
        return self._policy.generation.dimension

    async def embed_query(
        self,
        query: str,
        *,
        cancellation: CancellationSignal | None = None,
        correlation_id: str | None = None,
    ) -> tuple[float, ...]:
        result = await self._embed(
            (query,),
            purpose=EmbeddingPurpose.RETRIEVAL_QUERY,
            cancellation=cancellation,
            correlation_id=correlation_id,
        )
        return result[0]

    async def embed_documents(
        self,
        documents: Sequence[str],
        *,
        cancellation: CancellationSignal | None = None,
        correlation_id: str | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        return await self._embed(
            tuple(documents),
            purpose=EmbeddingPurpose.RETRIEVAL_DOCUMENT,
            cancellation=cancellation,
            correlation_id=correlation_id,
        )

    async def aclose(self) -> None:
        await self._provider.aclose()

    async def _embed(
        self,
        texts: tuple[str, ...],
        *,
        purpose: EmbeddingPurpose,
        cancellation: CancellationSignal | None,
        correlation_id: str | None,
    ) -> tuple[tuple[float, ...], ...]:
        now = self._clock()
        request = EmbeddingRequest(
            inputs=tuple(
                EmbeddingInput(
                    index=index,
                    text=text,
                    estimated_tokens=self._token_estimator.estimate(text),
                )
                for index, text in enumerate(texts)
            ),
            purpose=purpose,
            expected_generation=self._policy.generation,
            deadline_at=now + timedelta(seconds=self._policy.timeout_seconds),
            budget=EmbeddingBudget(
                max_items=self._policy.max_items,
                max_input_bytes=self._policy.max_input_bytes,
                max_input_tokens=self._policy.max_input_tokens,
                max_cost_microusd=self._policy.max_cost_microusd,
            ),
            correlation_id=correlation_id or f"embedding-{uuid4()}",
            cancellation=cancellation,
        )
        result = await self._provider.embed(request)
        return tuple(vector.values for vector in result.vectors)
