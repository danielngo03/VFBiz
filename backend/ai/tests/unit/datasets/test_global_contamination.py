import json
import shutil
from pathlib import Path
from typing import cast

import pytest

from app.modules.datasets.application.evaluation.global_contamination import (
    ContaminationRecord,
    ContaminationSourceEvidence,
    build_untrusted_contamination_projection,
)
from app.modules.datasets.infrastructure.global_contamination_builder import (
    build_governed_global_contamination_report,
)
from app.modules.datasets.infrastructure.global_contamination_store import (
    write_global_contamination_report,
)

_DIGEST = "a" * 64
_EXTRACTOR_DIGEST = "e" * 64
_ALGORITHM_DIGEST = "f" * 64
ROOT = Path(__file__).resolve().parents[5]


def _record(product: str, record_id: str, text: str) -> ContaminationRecord:
    source_id = f"{product}.jsonl"
    source_digest = _DIGEST if product == "golden" else "b" * 64
    return ContaminationRecord(
        product=product,
        source_id=source_id,
        source_sha256=source_digest,
        record_id=record_id,
        family_id=f"family-{record_id}",
        text=text,
    )


def _evidence(product: str, count: int = 1) -> ContaminationSourceEvidence:
    return ContaminationSourceEvidence(
        product=product,
        source_id=f"{product}.jsonl",
        source_sha256=_DIGEST if product == "golden" else "b" * 64,
        extractor_id="test-v1",
        extractor_source_sha256=_EXTRACTOR_DIGEST,
        surface_count=count,
    )


def _report(
    golden: tuple[ContaminationRecord, ...],
    comparison: tuple[ContaminationRecord, ...],
) -> dict[str, object]:
    products = sorted({record.product for record in comparison})
    return build_untrusted_contamination_projection(
        golden_records=golden,
        comparison_records=comparison,
        source_evidence=(_evidence("golden", len(golden)),)
        + tuple(
            _evidence(product, sum(record.product == product for record in comparison))
            for product in products
        ),
        algorithm_source_sha256=_ALGORITHM_DIGEST,
    )


def test_report_fails_closed_when_required_products_are_missing() -> None:
    report = _report(
        (_record("golden", "g-1", "Tôi cần hỗ trợ."),),
        (_record("training", "t-1", "Một câu khác."),),
    )

    assert report["status"] == "incomplete"
    assert report["missing_products"] == ["knowledge", "red-team"]
    assert report["release_eligible"] is False
    assert report["semantic_equivalence_claimed"] is False


def test_report_rejects_exact_accent_insensitive_overlap() -> None:
    report = _report(
        (_record("golden", "g-1", "Giá phụ kiện hiện tại?"),),
        (_record("training", "t-1", "gia phu kien hien tai"),),
    )

    assert report["status"] == "failed"
    assert report["exact_overlap_count"] == 1
    assert report["lexical_near_overlap_count"] == 0


def test_report_counts_all_matches_while_truncating_examples() -> None:
    golden = tuple(_record("golden", f"g-{index}", "Trùng hoàn toàn") for index in range(11))
    comparison = tuple(
        _record("training", f"t-{index}", "trung hoan toan") for index in range(11)
    )
    report = build_untrusted_contamination_projection(
        golden_records=golden,
        comparison_records=comparison,
        source_evidence=(_evidence("golden", 11), _evidence("training", 11)),
        algorithm_source_sha256=_ALGORITHM_DIGEST,
        maximum_examples=3,
    )

    assert report["exact_overlap_count"] == 121
    examples = report["exact_overlap_examples"]
    assert isinstance(examples, list)
    assert len(cast(list[object], examples)) == 3
    assert report["exact_examples_truncated"] is True


def test_report_rejects_unbound_record_and_weakened_source_coverage() -> None:
    golden = (_record("golden", "g-1", "Một câu Golden."),)
    comparison = (_record("training", "t-1", "Một câu training."),)
    forged = ContaminationRecord(
        product="training",
        source_id="unrelated.jsonl",
        source_sha256="c" * 64,
        record_id="forged",
        family_id="forged-family",
        text="Nội dung thay thế",
    )

    with pytest.raises(ValueError, match="not bound"):
        build_untrusted_contamination_projection(
            golden_records=golden,
            comparison_records=(forged,),
            source_evidence=(_evidence("golden"), _evidence("training")),
            algorithm_source_sha256=_ALGORITHM_DIGEST,
        )
    report = _report(golden, comparison)
    assert report["required_products"] == ["knowledge", "red-team", "training"]
    assert report["status"] == "incomplete"


def test_governed_builder_resolves_complete_source_set_from_pinned_inventory(
    tmp_path: Path,
) -> None:
    inventory_relative = Path(
        "backend/ai/dataset-specs/evaluation/global-contamination-source-inventory-v1.json"
    )
    golden_relative = Path(
        "local-data/ai-datasets/candidate/evaluation/customer-assistant-golden-v1/"
        "7189b908c558ef60c8b7c8a418a0d97803d7c60ff52facb228ade2e8d4c2e020/"
        "cases.jsonl"
    )
    inventory_path = tmp_path / inventory_relative
    golden_path = tmp_path / golden_relative
    inventory_path.parent.mkdir(parents=True)
    golden_path.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / inventory_relative, inventory_path)
    shutil.copyfile(ROOT / golden_relative, golden_path)
    training_root = tmp_path / "local-data/ai-datasets/candidate/tuning"
    first_training = training_root / "first/canonical/train.jsonl"
    first_training.parent.mkdir(parents=True)
    first_training.write_text(
        json.dumps(
            {
                "record_id": "t-1",
                "family_id": "training-family",
                "messages": [{"role": "user", "content": "Vui lòng làm rõ."}],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_governed_global_contamination_report(repository_root=tmp_path)

    assert report["golden_surface_count"] == 1320
    assert report["comparison_surface_count"] == 1
    assert report["status"] == "incomplete"
    assert report["source_inventory_sha256"] == (
        "131af17ba9d637a6637f80fb8f0c1798e77bf74bba3521c99cc7f67590daded4"
    )

    first_golden = json.loads(golden_path.read_text(encoding="utf-8").splitlines()[0])
    omitted_overlap = training_root / "second/canonical/train.jsonl"
    omitted_overlap.parent.mkdir(parents=True)
    omitted_overlap.write_text(
        json.dumps(
            {
                "record_id": "t-overlap",
                "family_id": "training-overlap",
                "messages": [first_golden["conversation"][0]],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    failed = build_governed_global_contamination_report(repository_root=tmp_path)
    assert failed["status"] == "failed"
    assert int(str(failed["exact_overlap_count"])) >= 1

    inventory_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not trusted"):
        build_governed_global_contamination_report(repository_root=tmp_path)


def _governed_report_fixture(tmp_path: Path) -> dict[str, object]:
    inventory_relative = Path(
        "backend/ai/dataset-specs/evaluation/global-contamination-source-inventory-v1.json"
    )
    golden_relative = Path(
        "local-data/ai-datasets/candidate/evaluation/customer-assistant-golden-v1/"
        "7189b908c558ef60c8b7c8a418a0d97803d7c60ff52facb228ade2e8d4c2e020/"
        "cases.jsonl"
    )
    for relative in (inventory_relative, golden_relative):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    training = (
        tmp_path
        / "local-data/ai-datasets/candidate/tuning/fixture/canonical/train.jsonl"
    )
    training.parent.mkdir(parents=True)
    training.write_text(
        json.dumps(
            {
                "record_id": "t-1",
                "family_id": "training-family",
                "messages": [{"role": "user", "content": "Một câu training."}],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return build_governed_global_contamination_report(repository_root=tmp_path)


def test_report_store_recomputes_governed_report_and_is_private(tmp_path: Path) -> None:
    report = _governed_report_fixture(tmp_path)
    target = write_global_contamination_report(
        report=report,
        root=tmp_path / "evidence",
        repository_root=tmp_path,
    )

    assert target == write_global_contamination_report(
        report=report,
        root=tmp_path / "evidence",
        repository_root=tmp_path,
    )
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.parent.stat().st_mode & 0o777 == 0o700
    tampered = {**report, "status": "passed"}
    with pytest.raises(ValueError, match="does not match"):
        write_global_contamination_report(
            report=tampered,
            root=tmp_path / "forged",
            repository_root=tmp_path,
        )


def test_raw_projection_cannot_be_stored_or_fake_positive_coverage(
    tmp_path: Path,
) -> None:
    golden = (_record("golden", "g-1", "Tôi cần hỗ trợ sạc tại nhà."),)
    comparison = (_record("training", "t-1", "Tôi cần hỗ trợ sạc."),)
    with pytest.raises(ValueError, match="at least one parsed surface"):
        build_untrusted_contamination_projection(
            golden_records=golden,
            comparison_records=comparison,
            source_evidence=(
                _evidence("golden"),
                _evidence("training"),
                _evidence("knowledge", 0),
                _evidence("red-team", 0),
            ),
            algorithm_source_sha256=_ALGORITHM_DIGEST,
            semantic_threshold=1.0,
        )

    raw = _report(golden, comparison)
    with pytest.raises(ValueError, match="source inventory is not trusted"):
        write_global_contamination_report(
            report=raw,
            root=tmp_path / "forged",
            repository_root=tmp_path,
        )
