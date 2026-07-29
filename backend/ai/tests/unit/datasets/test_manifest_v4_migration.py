from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from app.modules.datasets.application.curation.manifest_migration import (
    LegacyDatasetImportEvidence,
    LegacyDatasetManifestImporter,
)
from app.modules.datasets.application.curation.release_manifest import (
    DatasetManifestV4SemanticValidator,
    LegacyDatasetManifestV3SemanticValidator,
)

ROOT = Path(__file__).parents[3]
MANIFEST_VALIDATOR = (
    ROOT / ".agents/skills/generate-synthetic-dataset/scripts/validate_manifest.py"
)
REPOSITORY_ROOT = ROOT.parents[1]


class ManifestContractAuthorityFixture:
    def __init__(self) -> None:
        self._legacy = self._validator(
            "contracts/ai/datasets/products/legacy-release-manifest-v3.schema.json"
        )
        self._v4 = self._validator(
            "contracts/ai/datasets/products/release-manifest.schema.json"
        )

    @staticmethod
    def _validator(path: str) -> Draft202012Validator:
        schema = json.loads((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))
        return Draft202012Validator(schema, format_checker=FormatChecker())

    def validate_legacy_candidate(self, manifest: dict[str, Any]) -> list[str]:
        return [
            *(error.message for error in self._legacy.iter_errors(manifest)),
            *LegacyDatasetManifestV3SemanticValidator().errors(manifest),
        ]

    def validate_v4_candidate(self, manifest: dict[str, Any]) -> list[str]:
        return [
            *(error.message for error in self._v4.iter_errors(manifest)),
            *DatasetManifestV4SemanticValidator().errors(manifest),
        ]


def legacy_importer() -> LegacyDatasetManifestImporter:
    return LegacyDatasetManifestImporter(ManifestContractAuthorityFixture())


def load_skill_manifest_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "dataset_manifest_validator_v4",
        MANIFEST_VALIDATOR,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(spec.name, None)


def legacy_candidate(*, purpose: str = "intent-ood") -> dict[str, object]:
    return {
        "release_id": "legacy-router-0.1.0",
        "dataset_id": "legacy-router",
        "version": "0.1.0",
        "status": "candidate",
        "purpose": purpose,
        "classification": "internal",
        "assistant_profiles": ["public_customer"],
        "source_ids": ["legacy-source"],
        "artifacts": [
            {
                "zone": "candidate",
                "content_address": f"sha256/aa/{'a' * 64}",
                "sha256": "a" * 64,
                "tree_hash": "b" * 64,
                "records": 10,
                "bytes": 100,
                "media_type": "application/x-ndjson",
            }
        ],
        "record_counts": {"candidate": 10, "accepted": 0, "rejected": 0},
        "split": {
            "strategy_revision": "legacy-family-v1",
            "family_hash": "c" * 64,
            "partitions": {"candidate": 10},
            "held_out_lock_state": "unlocked",
        },
        "quality_runs": [
            {
                "run_id": "legacy-quality-1",
                "validator_revision": "legacy-v1",
                "metrics": {"valid": 10},
                "evidence_digest": "d" * 64,
            }
        ],
        "known_limitations": [],
        "approval_evidence": [
            {
                "decision_id": "legacy-release-approval",
                "role": "release-owner",
                "actor_ref": "human:legacy-release-owner",
                "decision": "approved",
                "evidence_digest": "e" * 64,
                "decided_at": "2026-07-28T00:00:00Z",
            }
        ],
        "retention_policy_id": "candidate-v1",
        "deletion_method": "Delete the candidate and retain a lineage tombstone.",
        "rollback_target": None,
        "content_hash": "f" * 64,
        "created_at": "2026-07-28T00:00:00Z",
    }


def import_evidence() -> LegacyDatasetImportEvidence:
    return LegacyDatasetImportEvidence(
        source_revisions={"legacy-source": "legacy-revision-1"},
        source_artifact_digests={"legacy-source": f"sha256:{'1' * 64}"},
        payload_contract_id=(
            "https://vfbiz.example/contracts/ai/dataset-payload/classifier/v1"
        ),
        payload_revision="v1",
        payload_digest=f"sha256:{'2' * 64}",
        transformation_recipe_revision="legacy-import-v1",
        transformation_recipe_digest=f"sha256:{'3' * 64}",
        quality_authority_ref="dataset-quality:migration:legacy-router",
        quality_evidence_digest=f"sha256:{'4' * 64}",
        observed_at="2026-07-29T00:00:00Z",
    )


def released_v4_manifest() -> dict[str, object]:
    return {
        "release_id": "vivi-router-1.0.0",
        "dataset_id": "vivi-router",
        "version": "1.0.0",
        "status": "released",
        "asset_kind": "dataset-record",
        "allowed_use": "classifier-training",
        "task_families": ["intent-ood"],
        "modalities": ["text"],
        "trust_zone": "released",
        "processing_stage": "adjudicated",
        "payload_schema": {
            "contract_id": "classifier-v1",
            "revision": "v1",
            "digest": f"sha256:{'2' * 64}",
        },
        "export_profile": {
            "profile_id": "vertex-classifier-jsonl",
            "revision": "v1",
            "digest": f"sha256:{'3' * 64}",
        },
        "classification": "internal",
        "assistant_profiles": ["public_customer"],
        "source_ids": ["approved-source"],
        "provenance": {
            "sources": [
                {
                    "source_id": "approved-source",
                    "source_revision": "revision-1",
                    "artifact_digest": f"sha256:{'4' * 64}",
                }
            ],
            "transformation_recipe_revision": "router-v1",
            "transformation_recipe_digest": f"sha256:{'5' * 64}",
            "lineage_digest": f"sha256:{'6' * 64}",
        },
        "artifacts": [
            {
                "zone": "released",
                "content_address": f"sha256/aa/{'a' * 64}",
                "sha256": "a" * 64,
                "tree_hash": "b" * 64,
                "records": 10,
                "bytes": 100,
                "media_type": "application/x-ndjson",
            }
        ],
        "record_counts": {"candidate": 10, "accepted": 10, "rejected": 0},
        "split_lock": {
            "state": "locked",
            "strategy_revision": "family-v1",
            "family_hash": "c" * 64,
            "partitions": {"train": 8, "validation": 2},
            "locked_at": "2026-07-29T00:00:00Z",
        },
        "quality_evidence": [
            {
                "run_id": "quality-1",
                "validator_revision": "v1",
                "artifact_digest": f"sha256:{'a' * 64}",
                "evidence_digest": f"sha256:{'d' * 64}",
                "authority_ref": "dataset-quality:run:quality-1",
                "state": "verified",
                "observed_at": "2026-07-29T00:00:00Z",
                "expires_at": "2027-07-29T00:00:00Z",
                "revoked_at": None,
            }
        ],
        "known_limitations": [],
        "approval_evidence": [
            {
                "decision_id": "data-1",
                "role": "data-owner",
                "actor_ref": "human:data:1",
                "decision": "approved",
                "evidence_digest": f"sha256:{'e' * 64}",
                "decided_at": "2026-07-29T00:00:00Z",
            },
            {
                "decision_id": "release-1",
                "role": "release-owner",
                "actor_ref": "human:release:1",
                "decision": "approved",
                "evidence_digest": f"sha256:{'f' * 64}",
                "decided_at": "2026-07-29T00:01:00Z",
            },
        ],
        "retention_policy_id": "training-v1",
        "deletion_method": "Delete payload and retain a lineage tombstone.",
        "rollback_target": None,
        "content_hash": "ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb",
        "created_at": "2026-07-29T00:00:00Z",
    }


def test_legacy_import_rejects_non_candidate_authority_state() -> None:
    manifest = legacy_candidate()
    manifest["status"] = "released"

    with pytest.raises(ValueError, match="candidate"):
        legacy_importer().import_candidate(manifest, import_evidence())


def test_legacy_import_validates_v3_schema_before_assigning_v4_identity() -> None:
    manifest = legacy_candidate()
    manifest["version"] = 123
    manifest["unexpected_authority"] = "must-not-cross-boundary"

    with pytest.raises(ValueError, match="canonical v3 contract"):
        legacy_importer().import_candidate(manifest, import_evidence())


def test_legacy_import_is_deterministic_and_drops_legacy_approvals() -> None:
    importer = legacy_importer()

    first = importer.import_candidate(legacy_candidate(), import_evidence())
    second = importer.import_candidate(legacy_candidate(), import_evidence())

    assert first == second
    assert first.manifest["status"] == "candidate"
    assert first.manifest["allowed_use"] == "classifier-training"
    assert first.manifest["task_families"] == ["intent-ood"]
    assert first.manifest["approval_evidence"] == []
    assert first.manifest["quality_evidence"][0]["state"] == "pending"
    assert first.manifest["provenance"]["lineage_digest"] == first.migration_digest
    assert first.source_manifest_digest.startswith("sha256:")
    assert first.migration_digest.startswith("sha256:")
    assert load_skill_manifest_validator().validate_manifest(first.manifest) == []


def test_legacy_multimodal_purpose_requires_explicit_reclassification() -> None:
    with pytest.raises(ValueError, match="explicit target classification"):
        legacy_importer().import_candidate(
            legacy_candidate(purpose="multimodal"),
            import_evidence(),
        )


def test_v4_semantic_validator_accepts_consistent_release() -> None:
    assert DatasetManifestV4SemanticValidator().errors(released_v4_manifest()) == []


def test_skill_validator_uses_canonical_v4_semantics() -> None:
    validator = load_skill_manifest_validator()

    assert validator.validate_manifest(released_v4_manifest()) == []


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda value: value["record_counts"].update({"rejected": 1}),
            "candidate count",
        ),
        (
            lambda value: value["split_lock"]["partitions"].update({"train": 7}),
            "partition total",
        ),
        (
            lambda value: value["quality_evidence"][0].update(
                {"artifact_digest": f"sha256:{'7' * 64}"}
            ),
            "artifact outside manifest",
        ),
        (
            lambda value: value["approval_evidence"][1].update(
                {"actor_ref": "human:data:1"}
            ),
            "distinct human actors",
        ),
        (
            lambda value: value["artifacts"][0].update(
                {"content_address": f"sha256/77/{'7' * 64}"}
            ),
            "content address",
        ),
        (
            lambda value: value.update({"content_hash": "9" * 64}),
            "content_hash",
        ),
        (
            lambda value: value["artifacts"].append(
                {
                    **value["artifacts"][0],
                    "content_address": f"sha256/bb/{'b' * 64}",
                    "sha256": "b" * 64,
                    "records": 0,
                }
            ),
            "every released artifact",
        ),
        (
            lambda value: value["quality_evidence"][0].update(
                {"expires_at": "2020-01-01T00:00:00Z"}
            ),
            "expired",
        ),
        (
            lambda value: value["provenance"]["sources"][0].update(
                {"source_revision": "candidate-input-unresolved"}
            ),
            "provenance must be resolved",
        ),
        (
            lambda value: value["approval_evidence"][1].update(
                {"decision_id": "data-1"}
            ),
            "decision ids must be unique",
        ),
        (
            lambda value: value["quality_evidence"][0].pop("expires_at"),
            "requires expiry",
        ),
        (
            lambda value: value["provenance"]["sources"][0].update(
                {"source_revision": "unknown"}
            ),
            "provenance must be resolved",
        ),
    ],
)
def test_v4_semantic_validator_fails_closed(
    mutate: Callable[[dict[str, Any]], None],
    expected: str,
) -> None:
    manifest = deepcopy(released_v4_manifest())
    mutate(manifest)

    assert any(
        expected in error
        for error in DatasetManifestV4SemanticValidator().errors(manifest)
    )
