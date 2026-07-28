from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.modules.datasets.domain.registry import RegistryInvariantError


class AssetKind(StrEnum):
    SOURCE_DOCUMENT = "source-document"
    DATASET_RECORD = "dataset-record"
    EVALUATION_CASE = "evaluation-case"
    SYNTHETIC_CANDIDATE = "synthetic-candidate"


class DatasetUse(StrEnum):
    KNOWLEDGE_INDEX = "knowledge-index"
    CLASSIFIER_TRAINING = "classifier-training"
    SFT = "sft"
    PREFERENCE = "preference"
    EMBEDDING = "embedding"
    RERANKER = "reranker"
    EVALUATION = "evaluation"
    RED_TEAM = "red-team"


class TaskFamily(StrEnum):
    FACTUAL_CITATION = "factual-citation"
    RETRIEVAL = "retrieval"
    INTENT_OOD = "intent-ood"
    CONVERSATION_QUALITY = "conversation-quality"
    TOOL_USE = "tool-use"
    REFUSAL_SAFETY = "refusal-safety"
    STATE_RESILIENCE = "state-resilience"


class Modality(StrEnum):
    TEXT = "text"
    DOCUMENT = "document"
    IMAGE = "image"
    AUDIO = "audio"


class SplitRole(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"
    GOLDEN = "golden"
    RED_TEAM = "red-team"


_TRAINING_USES = {
    DatasetUse.CLASSIFIER_TRAINING,
    DatasetUse.SFT,
    DatasetUse.PREFERENCE,
    DatasetUse.EMBEDDING,
    DatasetUse.RERANKER,
}


@dataclass(frozen=True, slots=True)
class DatasetClassification:
    """Orthogonal classification attached to each derived dataset artifact."""

    asset_kind: AssetKind
    allowed_use: DatasetUse
    task_families: tuple[TaskFamily, ...]
    modalities: tuple[Modality, ...]
    split_role: SplitRole
    split_family_id: str

    def __post_init__(self) -> None:
        if not self.task_families or len(set(self.task_families)) != len(self.task_families):
            raise RegistryInvariantError("task families must be non-empty and unique")
        if not self.modalities or len(set(self.modalities)) != len(self.modalities):
            raise RegistryInvariantError("modalities must be non-empty and unique")
        if not self.split_family_id.strip():
            raise RegistryInvariantError("split family ID is required")
        if self.split_role in {SplitRole.GOLDEN, SplitRole.TEST} and self.allowed_use not in {
            DatasetUse.EVALUATION,
            DatasetUse.RED_TEAM,
        }:
            raise RegistryInvariantError(
                "golden and held-out test artifacts cannot be used for training or knowledge"
            )
        if self.split_role is SplitRole.RED_TEAM and self.allowed_use is not DatasetUse.RED_TEAM:
            raise RegistryInvariantError("red-team splits are red-team-only")
        if self.asset_kind is AssetKind.EVALUATION_CASE and self.allowed_use in _TRAINING_USES:
            raise RegistryInvariantError("evaluation cases are permanently excluded from training")

    @property
    def is_training_artifact(self) -> bool:
        return self.allowed_use in _TRAINING_USES
