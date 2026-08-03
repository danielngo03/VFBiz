"""Provider adapters for the provider-neutral embedding contract."""

from app.infrastructure.embedding_providers.openai import OpenAIEmbeddingAdapter
from app.infrastructure.embedding_providers.policy import (
    EmbeddingAdapterPolicy,
    TeiDeploymentIdentity,
)
from app.infrastructure.embedding_providers.tei import TeiEmbeddingAdapter
from app.infrastructure.embedding_providers.vertex_embedding import (
    VertexEmbeddingAdapter,
    VertexEmbeddingDeploymentDescriptor,
)

__all__ = [
    "EmbeddingAdapterPolicy",
    "OpenAIEmbeddingAdapter",
    "TeiDeploymentIdentity",
    "TeiEmbeddingAdapter",
    "VertexEmbeddingAdapter",
    "VertexEmbeddingDeploymentDescriptor",
]
