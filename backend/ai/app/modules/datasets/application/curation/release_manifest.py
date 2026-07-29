"""Cross-field invariants for canonical Dataset Release Manifest v4."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, cast


class DatasetManifestV4SemanticValidator:
    """Validate authority relationships that JSON Schema cannot express."""

    def errors(self, manifest: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        status = manifest.get("status")
        counts = manifest.get("record_counts")
        candidate = accepted = rejected = None
        if isinstance(counts, dict):
            counts = cast(dict[str, Any], counts)
            candidate = counts.get("candidate")
            accepted = counts.get("accepted")
            rejected = counts.get("rejected")
        if (
            isinstance(candidate, int)
            and isinstance(accepted, int)
            and isinstance(rejected, int)
        ):
            decided = accepted + rejected
            if status in {"decision-ready", "released"} and candidate != decided:
                errors.append(
                    "decision-ready or released candidate count must equal "
                    "accepted plus rejected"
                )
            elif status not in {"decision-ready", "released"} and decided > candidate:
                errors.append("accepted plus rejected cannot exceed candidate count")

        expected_records = (
            accepted if status in {"decision-ready", "released"} else candidate
        )
        artifact_records = 0
        artifact_digests: set[str] = set()
        artifact_addresses: set[str] = set()
        ordered_artifact_hashes: list[str] = []
        artifacts = manifest.get("artifacts")
        if isinstance(artifacts, list):
            for item_value in cast(list[object], artifacts):
                if not isinstance(item_value, dict):
                    continue
                item = cast(dict[str, Any], item_value)
                records = item.get("records")
                if isinstance(records, int):
                    artifact_records += records
                sha256 = item.get("sha256")
                if isinstance(sha256, str):
                    ordered_artifact_hashes.append(sha256)
                    content_address = item.get("content_address")
                    if content_address != f"sha256/{sha256[:2]}/{sha256}":
                        errors.append("artifact content address must match sha256")
                    if (
                        f"sha256:{sha256}" in artifact_digests
                        or (
                            isinstance(content_address, str)
                            and content_address in artifact_addresses
                        )
                    ):
                        errors.append(
                            "artifact digests and content addresses must be unique"
                        )
                    artifact_digests.add(f"sha256:{sha256}")
                    if isinstance(content_address, str):
                        artifact_addresses.add(content_address)
        expected_content_hash = hashlib.sha256(
            "".join(ordered_artifact_hashes).encode()
        ).hexdigest()
        if ordered_artifact_hashes and manifest.get("content_hash") != expected_content_hash:
            errors.append("content_hash must bind the ordered artifact digests")
        if isinstance(expected_records, int) and artifact_records != expected_records:
            errors.append("artifact record total does not match manifest state")

        split = manifest.get("split_lock")
        partitions: object = None
        if isinstance(split, dict):
            split = cast(dict[str, Any], split)
            partitions = split.get("partitions")
        partition_records = (
            sum(
                value
                for value in cast(dict[str, object], partitions).values()
                if isinstance(value, int)
            )
            if isinstance(partitions, dict)
            else 0
        )
        if isinstance(expected_records, int) and partition_records != expected_records:
            errors.append("partition total does not match manifest state")

        quality_evidence = manifest.get("quality_evidence")
        verified_artifact_digests: set[str] = set()
        if isinstance(quality_evidence, list):
            for evidence_value in cast(list[object], quality_evidence):
                if not isinstance(evidence_value, dict):
                    continue
                evidence = cast(dict[str, Any], evidence_value)
                if evidence.get("artifact_digest") not in artifact_digests:
                    errors.append("quality evidence references artifact outside manifest")
                if status in {"decision-ready", "released"}:
                    current = True
                    if evidence.get("state") != "verified":
                        current = False
                        errors.append(
                            "decision-ready or released quality evidence must be verified"
                        )
                    if evidence.get("revoked_at") is not None:
                        current = False
                        errors.append(
                            "decision-ready or released quality evidence is revoked"
                        )
                    expires_at = evidence.get("expires_at")
                    if not isinstance(expires_at, str):
                        current = False
                        errors.append(
                            "decision-ready or released quality evidence requires expiry"
                        )
                    else:
                        try:
                            expiry = datetime.fromisoformat(
                                expires_at.replace("Z", "+00:00")
                            )
                            observed = datetime.fromisoformat(
                                str(evidence.get("observed_at", "")).replace(
                                    "Z", "+00:00"
                                )
                            )
                        except ValueError:
                            current = False
                            errors.append("quality evidence expiry is invalid")
                        else:
                            if expiry <= observed:
                                current = False
                                errors.append(
                                    "quality evidence expiry must follow observation"
                                )
                            if expiry <= datetime.now(UTC):
                                current = False
                                errors.append(
                                    "decision-ready or released quality evidence is expired"
                                )
                    if current:
                        artifact_digest = evidence.get("artifact_digest")
                        if isinstance(artifact_digest, str):
                            verified_artifact_digests.add(artifact_digest)
        if status in {"decision-ready", "released"} and (
            artifact_digests - verified_artifact_digests
        ):
            errors.append("every released artifact requires current verified evidence")

        approvals = manifest.get("approval_evidence")
        actors: list[str] = []
        decision_ids: list[str] = []
        if isinstance(approvals, list):
            for approval_value in cast(list[object], approvals):
                if not isinstance(approval_value, dict):
                    continue
                approval = cast(dict[str, Any], approval_value)
                actor_ref = approval.get("actor_ref")
                if isinstance(actor_ref, str):
                    actors.append(actor_ref)
                decision_id = approval.get("decision_id")
                if isinstance(decision_id, str):
                    decision_ids.append(decision_id)
        if len(actors) != len(set(actors)):
            errors.append("approval decisions must use distinct human actors")
        if len(decision_ids) != len(set(decision_ids)):
            errors.append("approval decision ids must be unique")

        source_ids = manifest.get("source_ids")
        provenance = manifest.get("provenance")
        provenance_sources: object = None
        if isinstance(provenance, dict):
            provenance = cast(dict[str, Any], provenance)
            provenance_sources = provenance.get("sources")
        observed_source_ids: set[str] = set()
        if isinstance(provenance_sources, list):
            for source_value in cast(list[object], provenance_sources):
                if not isinstance(source_value, dict):
                    continue
                source = cast(dict[str, Any], source_value)
                source_id = source.get("source_id")
                if isinstance(source_id, str):
                    observed_source_ids.add(source_id)
                if (
                    status in {"decision-ready", "released"}
                    and str(source.get("source_revision", "")).strip().lower()
                    in {
                        "candidate-input-unresolved",
                        "unresolved",
                        "unknown",
                    }
                ):
                    errors.append(
                        "decision-ready or released provenance must be resolved"
                    )
        if isinstance(source_ids, list) and {
            value for value in cast(list[object], source_ids) if isinstance(value, str)
        } != observed_source_ids:
            errors.append("provenance sources must match source_ids exactly")
        return errors


class LegacyDatasetManifestV3SemanticValidator:
    """Compatibility-only invariants used before importing a v3 candidate."""

    def errors(self, manifest: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        counts_value = manifest.get("record_counts")
        counts = (
            cast(dict[str, Any], counts_value)
            if isinstance(counts_value, dict)
            else {}
        )
        candidate = counts.get("candidate")
        accepted = counts.get("accepted")
        rejected = counts.get("rejected")
        if (
            isinstance(candidate, int)
            and isinstance(accepted, int)
            and isinstance(rejected, int)
        ):
            decided = accepted + rejected
            if manifest.get("status") == "released" and candidate != decided:
                errors.append(
                    "released candidate count must equal accepted plus rejected"
                )
            elif manifest.get("status") != "released" and decided > candidate:
                errors.append("accepted plus rejected cannot exceed candidate count")

        artifacts_value = manifest.get("artifacts")
        artifact_records = 0
        if isinstance(artifacts_value, list):
            for artifact_value in cast(list[object], artifacts_value):
                if not isinstance(artifact_value, dict):
                    continue
                artifact = cast(dict[str, Any], artifact_value)
                records = artifact.get("records")
                if isinstance(records, int):
                    artifact_records += records

        split_value = manifest.get("split")
        partitions: object = None
        if isinstance(split_value, dict):
            split = cast(dict[str, Any], split_value)
            partitions = split.get("partitions")
        partition_records = (
            sum(
                value
                for value in cast(dict[str, object], partitions).values()
                if isinstance(value, int)
            )
            if isinstance(partitions, dict)
            else 0
        )
        expected_records = (
            accepted if manifest.get("status") == "released" else candidate
        )
        if isinstance(expected_records, int):
            if artifact_records != expected_records:
                errors.append("artifact record total does not match manifest state")
            if partition_records != expected_records:
                errors.append("partition total does not match manifest state")

        approvals_value = manifest.get("approval_evidence")
        actors: list[str] = []
        if isinstance(approvals_value, list):
            for approval_value in cast(list[object], approvals_value):
                if not isinstance(approval_value, dict):
                    continue
                approval = cast(dict[str, Any], approval_value)
                actor_ref = approval.get("actor_ref")
                if isinstance(actor_ref, str):
                    actors.append(actor_ref)
        if len(actors) != len(set(actors)):
            errors.append("approval decisions must use distinct human actors")
        return errors
