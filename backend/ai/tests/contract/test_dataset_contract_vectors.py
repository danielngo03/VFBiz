from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

from app.modules.evaluation.domain import GraderCalibration

ROOT = Path(__file__).parents[4]
MANIFEST_VALIDATOR = (
    ROOT / "backend/ai/.agents/skills/generate-synthetic-dataset/scripts/validate_manifest.py"
)
GOLDEN_VALIDATOR = MANIFEST_VALIDATOR.with_name("validate_golden_case.py")
CONTRACT_REGISTRY = ROOT / "contracts/ai/index.json"
DATASET_SPECS = ROOT / "backend/ai/dataset-specs"
DATASET_MANIFEST_CONTRACT_IDS = {
    "https://vfbiz.example/contracts/ai/dataset-release-manifest/v3",
    "https://vfbiz.example/contracts/ai/dataset-release-manifest/v4",
}


def load_validator(path: Path, module_name: str) -> Any:
    scripts_dir = str(path.parent)
    sys.path.insert(0, scripts_dir)
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(scripts_dir)


def load_contract_registry() -> dict[str, dict[str, Any]]:
    registry = json.loads(CONTRACT_REGISTRY.read_text(encoding="utf-8"))
    references: dict[str, dict[str, Any]] = {}
    basenames: dict[str, dict[str, Any] | None] = {}
    for entry in registry["contracts"]:
        references[entry["contractId"]] = entry
        references[entry["canonicalPath"]] = entry
        paths = [entry["canonicalPath"], *entry["legacyPaths"]]
        for contract_path in paths:
            references[contract_path] = entry
            basename = Path(contract_path).name
            previous = basenames.get(basename)
            basenames[basename] = (
                entry if previous is None or previous["contractId"] == entry["contractId"] else None
            )
    for basename, entry in basenames.items():
        if entry is not None:
            references[basename] = entry
    return references


def evaluation_semantic_errors(contract_id: str, value: dict[str, Any]) -> list[str]:
    if contract_id.endswith("/source-intake-receipt/v1"):
        if value.get("content_revision") != f"sha256:{value.get('observed_sha256')}":
            return ["content revision must equal the observed SHA-256"]
        return []
    if contract_id.endswith("/source-register/v5"):
        origin = value.get("origin")
        if (
            isinstance(origin, dict)
            and origin.get("kind") in {"managed-upload", "local-bootstrap"}
            and value.get("source_revision") != value.get("content_revision")
        ):
            return ["managed source revision must equal its content revision"]
        return []
    if contract_id.endswith("/benchmark-definition/v2"):
        return fixed_usd_errors(
            cast(dict[str, Any], value["budgets"])["max_cost_usd"]
        )
    if contract_id.endswith("/run-request/v2"):
        return fixed_usd_errors(
            cast(dict[str, Any], value["budgets"])["maxCostUsd"]
        )
    if contract_id.endswith("/case-result/v1"):
        return fixed_usd_errors(
            cast(dict[str, Any], value["usage"])["cost_usd"]
        )
    if contract_id.endswith("/grader-calibration/v2"):
        matrix = cast(dict[str, int], value["confusion_matrix"])
        slices = cast(list[dict[str, Any]], value["slice_metrics"])
        try:
            GraderCalibration(
                grader_revision=cast(str, value["grader_revision"]),
                grader_definition_digest=cast(
                    str,
                    value["grader_definition_digest"],
                ),
                implementation_digest=cast(
                    str,
                    value["implementation_digest"],
                ),
                calibrated_at=parse_datetime(cast(str, value["calibrated_at"])),
                expires_at=parse_datetime(cast(str, value["expires_at"])),
                evidence_digest=cast(str, value["evidence_digest"]),
                human_labelled_suite_digest=cast(
                    str,
                    value["human_labelled_suite_digest"],
                ),
                sample_size=cast(int, value["sample_size"]),
                confusion_matrix=(
                    matrix["true_positive"],
                    matrix["true_negative"],
                    matrix["false_positive"],
                    matrix["false_negative"],
                ),
                balanced_accuracy=cast(float, value["balanced_accuracy"]),
                f1=cast(float, value["f1"]),
                slice_metrics=tuple(
                    (
                        cast(str, item["slice"]),
                        cast(int, item["sample_size"]),
                        cast(float, item["balanced_accuracy"]),
                        cast(float, item["f1"]),
                        cast(dict[str, int], item["confusion_matrix"])[
                            "true_positive"
                        ],
                        cast(dict[str, int], item["confusion_matrix"])[
                            "true_negative"
                        ],
                        cast(dict[str, int], item["confusion_matrix"])[
                            "false_positive"
                        ],
                        cast(dict[str, int], item["confusion_matrix"])[
                            "false_negative"
                        ],
                    )
                    for item in slices
                ),
            )
        except ValueError as error:
            return [str(error)]
        return []
    if contract_id.endswith("/grader-calibration/v1"):
        matrix = value["confusion_matrix"]
        assert isinstance(matrix, dict)
        counts: list[int] = [
            cast(int, matrix["true_positive"]),
            cast(int, matrix["true_negative"]),
            cast(int, matrix["false_positive"]),
            cast(int, matrix["false_negative"]),
        ]
        errors: list[str] = []
        if sum(counts) != value["sample_size"]:
            errors.append("confusion matrix total must equal sample_size")
        true_positive, true_negative, false_positive, false_negative = counts
        positive_denominator = true_positive + false_negative
        negative_denominator = true_negative + false_positive
        if positive_denominator == 0 or negative_denominator == 0:
            errors.append("calibration must contain positive and negative examples")
            return errors
        positive_recall = true_positive / positive_denominator
        negative_recall = true_negative / negative_denominator
        expected_balanced_accuracy = (positive_recall + negative_recall) / 2
        f1_denominator = 2 * true_positive + false_positive + false_negative
        if f1_denominator == 0:
            errors.append("calibration must contain positive predictions or labels")
            return errors
        expected_f1 = (2 * true_positive) / f1_denominator
        if abs(value["balanced_accuracy"] - expected_balanced_accuracy) > 1e-6:
            errors.append("balanced_accuracy must match confusion matrix")
        if abs(value["f1"] - expected_f1) > 1e-6:
            errors.append("f1 must match confusion matrix")
        if parse_datetime(value["expires_at"]) <= parse_datetime(value["calibrated_at"]):
            errors.append("calibration expiry must be after calibrated_at")
        slices = [item["slice"] for item in value["slice_metrics"]]
        if len(slices) != len(set(slices)):
            errors.append("calibration slices must be unique")
        return errors
    if contract_id.endswith("/run-result/v1"):
        money_errors = fixed_usd_errors(
            cast(dict[str, Any], value["budget_usage"])["cost_usd"]
        )
        run_counts = cast(dict[str, int], value["case_counts"])
        terminal = sum(run_counts[name] for name in ("valid", "invalid", "failed", "cancelled"))
        if terminal != run_counts["evaluated"]:
            return [*money_errors, "terminal case counts must equal evaluated"]
        if value["state"] == "decision_ready" and (
            run_counts["evaluated"] != run_counts["expected"]
            or run_counts["invalid"] != 0
            or run_counts["failed"] != 0
            or run_counts["cancelled"] != 0
        ):
            return [*money_errors, "decision_ready requires complete valid case set"]
        if parse_datetime(value["completed_at"]) < parse_datetime(value["started_at"]):
            return [*money_errors, "completed_at must not precede started_at"]
        return money_errors
    if contract_id.endswith("/evidence-bundle/v1") and value["recommendation"] == "recommend":
        required_graders = value["required_grader_revisions"]
        calibrated_graders = [item["grader_revision"] for item in value["grader_calibrations"]]
        if (
            len(required_graders) != len(calibrated_graders)
            or not set(required_graders).issubset(calibrated_graders)
            or len(calibrated_graders) != len(set(calibrated_graders))
        ):
            return ["recommendation requires one calibration per required grader"]
    return []


def fixed_usd_errors(value: object) -> list[str]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ["evaluation cost must use bounded micro-USD precision"]
    decimal_value = Decimal(str(value))
    if (
        decimal_value < 0
        or decimal_value > Decimal("1000000")
        or decimal_value != decimal_value.quantize(Decimal("0.000001"))
    ):
        return ["evaluation cost must use bounded micro-USD precision"]
    return []


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_dataset_contract_vectors_match_python_validator() -> None:
    manifest_validator = load_validator(MANIFEST_VALIDATOR, "validate_manifest")
    golden_validator = load_validator(GOLDEN_VALIDATOR, "validate_golden_case")
    vectors: list[dict[str, Any]] = json.loads(
        (ROOT / "contracts/ai/test-vectors/dataset-contracts.json").read_text(encoding="utf-8")
    )
    registry = load_contract_registry()
    for vector in vectors:
        entry = registry.get(vector["schema"])
        assert entry is not None, vector["id"]
        schema = json.loads((ROOT / entry["canonicalPath"]).read_text(encoding="utf-8"))
        assert schema["$id"] == entry["contractId"]
        validator: Any = Draft202012Validator(schema, format_checker=FormatChecker())
        schema_valid = validator.is_valid(vector["value"])
        semantic_valid = (
            not manifest_validator.semantic_errors(vector["value"])
            if entry["contractId"] in DATASET_MANIFEST_CONTRACT_IDS
            else not golden_validator.semantic_errors(vector["value"])
            if entry["contractId"] == "https://vfbiz.example/contracts/ai/golden-case/v2"
            else not evaluation_semantic_errors(entry["contractId"], vector["value"])
        )
        observed = schema_valid and semantic_valid
        assert observed is vector["valid"], vector["id"]


def test_historical_dataset_evidence_is_content_addressed_and_resolvable() -> None:
    index = json.loads(
        (DATASET_SPECS / "evidence-index/public-intake-checkpoints.json").read_text(
            encoding="utf-8"
        )
    )
    entries = {entry["index_id"]: entry for entry in index["entries"]}
    assert entries
    for entry in entries.values():
        assert entry["immutable_ref"] == f"sha256:{entry['sha256']}"
        locator = entry["object_locator"]
        assert locator.startswith("repo:")
        artifact = ROOT / locator.removeprefix("repo:")
        assert artifact.is_file()
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == entry["sha256"]

    catalog = DATASET_SPECS / "catalog/sources"
    for source_path in catalog.rglob("*.json"):
        source = json.loads(source_path.read_text(encoding="utf-8"))
        for reference in source.get("evidence_refs", []):
            index_id, entry_id = reference.removeprefix("evidence-index:").split("#", 1)
            assert index_id == index["index_id"], source_path
            assert entry_id in entries, source_path
        migration_reference = source.get("provenance", {}).get("migration_evidence_ref")
        if migration_reference is not None:
            index_id, entry_id = migration_reference.removeprefix("evidence-index:").split(
                "#", 1
            )
            assert index_id == index["index_id"], source_path
            assert entry_id in entries, source_path
