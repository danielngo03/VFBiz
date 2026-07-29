"""Import legacy Dataset Manifest v3 candidates into canonical v4 candidates."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Final, Protocol, cast


class DatasetManifestContractAuthority(Protocol):
    """Schema authority injected at the application boundary."""

    def validate_legacy_candidate(self, manifest: dict[str, Any]) -> list[str]: ...

    def validate_v4_candidate(self, manifest: dict[str, Any]) -> list[str]: ...


@dataclass(frozen=True, slots=True)
class LegacyDatasetImportEvidence:
    source_revisions: Mapping[str, str]
    source_artifact_digests: Mapping[str, str]
    payload_contract_id: str
    payload_revision: str
    payload_digest: str
    transformation_recipe_revision: str
    transformation_recipe_digest: str
    quality_authority_ref: str
    quality_evidence_digest: str
    observed_at: str


@dataclass(frozen=True, slots=True)
class LegacyDatasetImportResult:
    manifest: dict[str, Any]
    source_manifest_digest: str
    migration_digest: str


@dataclass(frozen=True, slots=True)
class _PurposeClassification:
    asset_kind: str
    allowed_use: str
    task_families: tuple[str, ...]
    modalities: tuple[str, ...] = ("text",)


_PURPOSES: Final[dict[str, _PurposeClassification]] = {
    "knowledge": _PurposeClassification(
        asset_kind="source-document",
        allowed_use="knowledge-index",
        task_families=("factual-citation",),
        modalities=("document",),
    ),
    "retrieval-evaluation": _PurposeClassification(
        asset_kind="evaluation-case",
        allowed_use="evaluation",
        task_families=("retrieval",),
    ),
    "intent-ood": _PurposeClassification(
        asset_kind="dataset-record",
        allowed_use="classifier-training",
        task_families=("intent-ood",),
    ),
    "conversation-quality": _PurposeClassification(
        asset_kind="dataset-record",
        allowed_use="sft",
        task_families=("conversation-quality",),
    ),
    "tool-evaluation": _PurposeClassification(
        asset_kind="evaluation-case",
        allowed_use="evaluation",
        task_families=("tool-use",),
    ),
    "refusal-safety": _PurposeClassification(
        asset_kind="evaluation-case",
        allowed_use="evaluation",
        task_families=("refusal-safety",),
    ),
    "red-team": _PurposeClassification(
        asset_kind="evaluation-case",
        allowed_use="red-team",
        task_families=("refusal-safety",),
    ),
    "state-resilience": _PurposeClassification(
        asset_kind="evaluation-case",
        allowed_use="evaluation",
        task_families=("state-resilience",),
    ),
}


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json(value)).hexdigest()}"


class LegacyDatasetManifestImporter:
    """Convert an importable v3 candidate without inheriting release authority."""

    def __init__(self, contracts: DatasetManifestContractAuthority) -> None:
        self._contracts = contracts

    def import_candidate(
        self,
        legacy: dict[str, Any],
        evidence: LegacyDatasetImportEvidence,
    ) -> LegacyDatasetImportResult:
        legacy_contract_errors = self._contracts.validate_legacy_candidate(legacy)
        if legacy_contract_errors:
            raise ValueError(
                "legacy manifest violates canonical v3 contract: "
                + "; ".join(legacy_contract_errors)
            )
        if legacy.get("status") != "candidate":
            raise ValueError("legacy manifest must remain candidate before v4 import")

        purpose = legacy.get("purpose")
        if purpose == "multimodal":
            raise ValueError(
                "legacy multimodal purpose requires explicit target classification"
            )
        classification = _PURPOSES.get(str(purpose))
        if classification is None:
            raise ValueError(f"unsupported legacy dataset purpose: {purpose}")

        source_ids = self._source_ids(legacy)
        provenance_sources: list[dict[str, str]] = []
        for source_id in source_ids:
            source_revision = evidence.source_revisions.get(source_id)
            artifact_digest = evidence.source_artifact_digests.get(source_id)
            if not source_revision or not artifact_digest:
                raise ValueError(f"missing import evidence for source: {source_id}")
            provenance_sources.append(
                {
                    "source_id": source_id,
                    "source_revision": source_revision,
                    "artifact_digest": artifact_digest,
                }
            )

        source_manifest_digest = _digest(legacy)
        migration_digest = _digest(
            {
                "contract": "dataset-release-manifest/v3-to-v4-import/v1",
                "source_manifest_digest": source_manifest_digest,
                "classification": asdict(classification),
                "evidence": asdict(evidence),
            }
        )
        artifacts = self._candidate_artifacts(legacy)
        artifact_digest = f"sha256:{artifacts[0]['sha256']}"
        split = legacy.get("split")
        if not isinstance(split, dict):
            raise ValueError("legacy split is required")
        split = cast(dict[str, Any], split)
        counts = legacy.get("record_counts")
        if not isinstance(counts, dict):
            raise ValueError("legacy candidate record count is required")
        counts = cast(dict[str, Any], counts)
        if not isinstance(counts.get("candidate"), int):
            raise ValueError("legacy candidate record count is required")
        candidate_count = cast(int, counts["candidate"])
        legacy_profiles = cast(list[str], legacy["assistant_profiles"])
        legacy_partitions = cast(dict[str, int], split["partitions"])
        legacy_limitations = cast(list[str], legacy.get("known_limitations", []))

        manifest: dict[str, Any] = {
            "release_id": f"{legacy['release_id']}.v4-import",
            "dataset_id": legacy["dataset_id"],
            "version": legacy["version"],
            "status": "candidate",
            "asset_kind": classification.asset_kind,
            "allowed_use": classification.allowed_use,
            "task_families": list(classification.task_families),
            "modalities": list(classification.modalities),
            "trust_zone": "candidate",
            "processing_stage": "normalized",
            "payload_schema": {
                "contract_id": evidence.payload_contract_id,
                "revision": evidence.payload_revision,
                "digest": evidence.payload_digest,
            },
            "classification": legacy["classification"],
            "assistant_profiles": list(legacy_profiles),
            "source_ids": source_ids,
            "provenance": {
                "sources": provenance_sources,
                "transformation_recipe_revision": (
                    evidence.transformation_recipe_revision
                ),
                "transformation_recipe_digest": (
                    evidence.transformation_recipe_digest
                ),
                "lineage_digest": migration_digest,
            },
            "artifacts": artifacts,
            "record_counts": {
                "candidate": candidate_count,
                "accepted": 0,
                "rejected": 0,
            },
            "split_lock": {
                "state": split["held_out_lock_state"],
                "strategy_revision": split["strategy_revision"],
                "family_hash": split["family_hash"],
                "partitions": dict(legacy_partitions),
                **(
                    {"locked_at": split["held_out_locked_at"]}
                    if split.get("held_out_lock_state") == "locked"
                    else {}
                ),
            },
            "quality_evidence": [
                {
                    "run_id": f"legacy-import:{legacy['release_id']}",
                    "validator_revision": "legacy-import-v1",
                    "artifact_digest": artifact_digest,
                    "evidence_digest": evidence.quality_evidence_digest,
                    "authority_ref": evidence.quality_authority_ref,
                    "state": "pending",
                    "observed_at": evidence.observed_at,
                }
            ],
            "known_limitations": [
                *legacy_limitations,
                "Imported from v3; independent v4 quality review is required.",
            ],
            "approval_evidence": [],
            "retention_policy_id": legacy["retention_policy_id"],
            "deletion_method": legacy["deletion_method"],
            "rollback_target": None,
            "created_at": evidence.observed_at,
        }
        manifest["content_hash"] = hashlib.sha256(
            "".join(item["sha256"] for item in artifacts).encode()
        ).hexdigest()
        v4_contract_errors = self._contracts.validate_v4_candidate(manifest)
        if v4_contract_errors:
            raise ValueError(
                "imported manifest violates canonical v4 contract: "
                + "; ".join(v4_contract_errors)
            )
        return LegacyDatasetImportResult(
            manifest=manifest,
            source_manifest_digest=source_manifest_digest,
            migration_digest=migration_digest,
        )

    @staticmethod
    def _source_ids(legacy: dict[str, Any]) -> list[str]:
        source_ids = legacy.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids:
            raise ValueError("legacy source_ids are required")
        source_values = cast(list[object], source_ids)
        if not all(isinstance(item, str) and item for item in source_values):
            raise ValueError("legacy source_ids must contain non-empty strings")
        return cast(list[str], list(source_values))

    @staticmethod
    def _candidate_artifacts(legacy: dict[str, Any]) -> list[dict[str, Any]]:
        artifacts = legacy.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError("legacy artifacts are required")
        artifact_values = cast(list[object], artifacts)
        converted: list[dict[str, Any]] = []
        for item in artifact_values:
            if not isinstance(item, dict):
                raise ValueError("legacy artifacts must be objects")
            converted.append({**cast(dict[str, Any], item), "zone": "candidate"})
        return converted
