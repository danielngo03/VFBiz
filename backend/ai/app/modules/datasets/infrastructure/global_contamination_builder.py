"""Registry-bound filesystem reader for global contamination evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from app.modules.datasets.application.evaluation.global_contamination import (
    GLOBAL_CONTAMINATION_REQUIRED_PRODUCTS,
    GLOBAL_CONTAMINATION_SEMANTIC_THRESHOLD,
    ContaminationRecord,
    ContaminationSourceEvidence,
    build_untrusted_contamination_projection,
    compute_global_contamination_report_digest,
)

_INVENTORY_RELATIVE_PATH = Path(
    "backend/ai/dataset-specs/evaluation/global-contamination-source-inventory-v1.json"
)
_INVENTORY_SHA256 = "131af17ba9d637a6637f80fb8f0c1798e77bf74bba3521c99cc7f67590daded4"
_EXTRACTORS = frozenset(
    {"golden-conversation-v1", "message-record-v1", "text-record-v1"}
)


@dataclass(frozen=True, slots=True)
class _SourceSpec:
    product: str
    relative_path: str
    expected_sha256: str
    extractor_id: str


def build_governed_global_contamination_report(
    *, repository_root: Path
) -> dict[str, object]:
    """Resolve the exact source set from a pinned Data Governance inventory."""

    root = repository_root.resolve(strict=True)
    inventory_path = root / _INVENTORY_RELATIVE_PATH
    if inventory_path.is_symlink() or not inventory_path.is_file():
        raise ValueError("global contamination source inventory is not trusted")
    inventory_bytes = inventory_path.read_bytes()
    inventory_sha256 = hashlib.sha256(inventory_bytes).hexdigest()
    if inventory_sha256 != _INVENTORY_SHA256:
        raise ValueError("global contamination source inventory is not trusted")
    inventory = _parse_inventory(inventory_bytes)
    specs = _resolve_inventory(root, inventory)
    extractor_digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    algorithm_path = (
        Path(__file__).parents[1]
        / "application"
        / "evaluation"
        / "global_contamination.py"
    )
    algorithm_digest = hashlib.sha256(algorithm_path.read_bytes()).hexdigest()
    records: list[ContaminationRecord] = []
    evidence: list[ContaminationSourceEvidence] = []
    for source in specs:
        path = _safe_source_path(root, source.relative_path)
        payload = path.read_bytes()
        observed_digest = hashlib.sha256(payload).hexdigest()
        if source.expected_sha256 and observed_digest != source.expected_sha256:
            raise ValueError(f"source digest mismatch: {source.relative_path}")
        extracted = _extract_records(source, observed_digest, payload)
        records.extend(extracted)
        evidence.append(
            ContaminationSourceEvidence(
                product=source.product,
                source_id=source.relative_path,
                source_sha256=observed_digest,
                extractor_id=source.extractor_id,
                extractor_source_sha256=extractor_digest,
                surface_count=len(extracted),
            )
        )
    report = build_untrusted_contamination_projection(
        golden_records=tuple(record for record in records if record.product == "golden"),
        comparison_records=tuple(
            record for record in records if record.product != "golden"
        ),
        source_evidence=tuple(evidence),
        algorithm_source_sha256=algorithm_digest,
        semantic_threshold=GLOBAL_CONTAMINATION_SEMANTIC_THRESHOLD,
    )
    report["source_inventory_id"] = inventory["inventory_id"]
    report["source_inventory_sha256"] = inventory_sha256
    report["source_inventory_semantic_digest"] = inventory["semantic_digest"]
    report["authority_class"] = "inventory-governed-v1"
    report["report_digest"] = compute_global_contamination_report_digest(report)
    return report


def verify_governed_global_contamination_report(
    *, report: dict[str, object], repository_root: Path
) -> None:
    """Require byte-for-byte semantic parity with the governed filesystem build."""

    expected = build_governed_global_contamination_report(
        repository_root=repository_root
    )
    if report != expected:
        raise ValueError(
            "contamination report does not match the governed source inventory"
        )


def _parse_inventory(payload: bytes) -> dict[str, object]:
    try:
        value: object = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("global contamination source inventory is unreadable") from error
    if not isinstance(value, dict):
        raise ValueError("global contamination source inventory must be an object")
    inventory = cast(dict[str, object], value)
    supplied_digest = inventory.get("semantic_digest")
    basis = {key: item for key, item in inventory.items() if key != "semantic_digest"}
    canonical = json.dumps(
        basis, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if supplied_digest != hashlib.sha256(canonical).hexdigest():
        raise ValueError("global contamination source inventory digest mismatch")
    required_products = inventory.get("required_products")
    if not isinstance(required_products, list):
        raise ValueError("global contamination source inventory weakens product policy")
    required_values = cast(list[object], required_products)
    if not all(isinstance(item, str) for item in required_values) or cast(
        list[str], required_values
    ) != sorted(GLOBAL_CONTAMINATION_REQUIRED_PRODUCTS):
        raise ValueError("global contamination source inventory weakens product policy")
    return inventory


def _resolve_inventory(root: Path, inventory: dict[str, object]) -> tuple[_SourceSpec, ...]:
    raw_rules = inventory.get("source_rules")
    if not isinstance(raw_rules, list):
        raise ValueError("global contamination source inventory has no rules")
    rules = tuple(_rule(value) for value in cast(list[object], raw_rules))
    products = [str(rule["product"]) for rule in rules]
    if sorted(products) != ["golden", "knowledge", "red-team", "training"]:
        raise ValueError("global contamination source inventory has invalid product rules")
    specs: list[_SourceSpec] = []
    seen_paths: set[str] = set()
    for rule in rules:
        if rule["mode"] == "exact":
            paths = (str(rule["relative_path"]),)
        else:
            paths = _glob_rule(root, rule)
        for relative_path in paths:
            if relative_path in seen_paths:
                raise ValueError("global contamination source inventory aliases a source")
            seen_paths.add(relative_path)
            specs.append(
                _SourceSpec(
                    product=str(rule["product"]),
                    relative_path=relative_path,
                    expected_sha256=str(rule.get("expected_sha256", "")),
                    extractor_id=str(rule["extractor_id"]),
                )
            )
    if sum(spec.product == "golden" for spec in specs) != 1:
        raise ValueError("global contamination inventory must resolve one Golden source")
    return tuple(sorted(specs, key=lambda item: item.relative_path))


def _rule(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("global contamination source rule must be an object")
    rule = cast(dict[str, object], value)
    if rule.get("extractor_id") not in _EXTRACTORS:
        raise ValueError("global contamination source rule has unknown extractor")
    if rule.get("mode") not in {"exact", "glob"}:
        raise ValueError("global contamination source rule has invalid mode")
    return rule


def _glob_rule(root: Path, rule: dict[str, object]) -> tuple[str, ...]:
    relative_root = Path(str(rule.get("root", "")))
    pattern = str(rule.get("pattern", ""))
    if relative_root.is_absolute() or ".." in relative_root.parts or not pattern:
        raise ValueError("global contamination glob rule is unsafe")
    source_root = root / relative_root
    if not source_root.exists():
        return ()
    if source_root.is_symlink() or not source_root.is_dir():
        raise ValueError("global contamination glob root is unsafe")
    paths = tuple(path for path in source_root.glob(pattern) if path.is_file())
    if any(path.is_symlink() for path in paths):
        raise ValueError("global contamination glob matched a symlink")
    return tuple(str(path.relative_to(root)) for path in sorted(paths))


def _safe_source_path(repository_root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("source path must be repository-relative without traversal")
    path = repository_root / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"source is not a regular file: {relative_path}")
    resolved = path.resolve(strict=True)
    if repository_root not in resolved.parents:
        raise ValueError("source path escapes repository root")
    return resolved


def _extract_records(
    source: _SourceSpec, source_sha256: str, payload: bytes
) -> tuple[ContaminationRecord, ...]:
    rows = _parse_jsonl(payload)
    records: list[ContaminationRecord] = []
    for line_number, row in enumerate(rows, start=1):
        record_id = str(row.get("case_id") or row.get("record_id") or line_number)
        family_id = str(row.get("split_family_id") or row.get("family_id") or record_id)
        surfaces = _extract_surfaces(source.extractor_id, row)
        if not surfaces:
            location = f"{source.relative_path}:{line_number}"
            raise ValueError(f"source row has no extractable text: {location}")
        for surface_index, text in enumerate(surfaces):
            records.append(
                ContaminationRecord(
                    product=source.product,
                    source_id=source.relative_path,
                    source_sha256=source_sha256,
                    record_id=f"{record_id}:{surface_index}",
                    family_id=family_id,
                    text=text,
                )
            )
    return tuple(records)


def _parse_jsonl(payload: bytes) -> tuple[dict[str, object], ...]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("source is not UTF-8 JSONL") from error
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value: object = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSONL at line {line_number}") from error
        if not isinstance(value, dict):
            raise ValueError(f"JSONL row {line_number} must be an object")
        rows.append(cast(dict[str, object], value))
    if not rows:
        raise ValueError("source JSONL must not be empty")
    return tuple(rows)


def _extract_surfaces(extractor_id: str, row: dict[str, object]) -> tuple[str, ...]:
    if extractor_id == "golden-conversation-v1":
        return _message_contents(row.get("conversation"))
    if extractor_id == "message-record-v1":
        return _message_contents(row.get("messages"))
    value = row.get("text") or row.get("content")
    return (value,) if isinstance(value, str) and value.strip() else ()


def _message_contents(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    contents: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            continue
        content = cast(dict[str, object], item).get("content")
        if isinstance(content, str) and content.strip():
            contents.append(content)
    return tuple(contents)


__all__ = [
    "build_governed_global_contamination_report",
    "verify_governed_global_contamination_report",
]
