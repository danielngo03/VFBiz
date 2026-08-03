from __future__ import annotations

from typing import Any

from app.modules.datasets.application.curation.synthetic_text_quality import (
    SyntheticTextQualityPolicy,
    assess_synthetic_text_quality,
)
from app.modules.datasets.application.curation.synthetic_tuning_v4_authority import (
    VIVI_BEHAVIOR_SYNTHETIC_V4_AUTHORITY,
)
from app.modules.datasets.application.curation.synthetic_tuning_v4_generator import (
    build_v4_candidate,
)


def _record(
    record_id: str,
    split: str,
    assistant: str,
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "split": split,
        "messages": [
            {"role": "user", "content": f"Yêu cầu riêng {record_id}."},
            {"role": "assistant", "content": assistant},
        ],
        "lineage": {
            "response_component_ids": [
                f"response-prefix:{record_id}",
                f"response-bridge:{record_id}",
                f"response-tail:{record_id}",
            ]
        },
    }


def test_text_gate_rejects_unique_ids_wrapped_around_one_template() -> None:
    records = [
        _record(
            f"train-{index}",
            "train",
            f"Mình cần làm rõ một điểm trước khi hỗ trợ trường hợp {index}.",
        )
        for index in range(10)
    ]

    assessment = assess_synthetic_text_quality(
        records,
        policy=SyntheticTextQualityPolicy(
            maximum_prefix_share=0.2,
            cross_split_similarity_threshold=1.0,
        ),
    )

    assert not assessment.accepted
    assert assessment.maximum_prefix_share == {"train": 1.0}
    assert any(
        error.startswith("text-prefix-concentration:train:10/10:")
        for error in assessment.errors
    )


def test_text_gate_detects_cross_split_near_duplicate_and_implementation_term() -> None:
    assessment = assess_synthetic_text_quality(
        (
            _record(
                "train-1",
                "train",
                "Mình cần kiểm tra lineage trước khi xác nhận kết quả.",
            ),
            _record(
                "test-1",
                "test",
                "Mình cần kiểm tra lineage trước khi xác nhận kết quả nhé.",
            ),
        ),
        policy=SyntheticTextQualityPolicy(
            maximum_prefix_share=1.0,
            cross_split_similarity_threshold=0.85,
        ),
    )

    assert not assessment.accepted
    assert assessment.cross_split_near_duplicate_count == 1
    assert assessment.implementation_term_count == 2
    assert "cross-split-near-duplicate-count:1" in assessment.errors
    assert any(error.startswith("implementation-term:") for error in assessment.errors)


def test_text_gate_cannot_be_evaded_with_punctuation_or_multiword_terms() -> None:
    sensitive_record_id = "customer@example.com"
    assessment = assess_synthetic_text_quality(
        (
            _record(
                sensitive_record_id,
                "train",
                "Mình cần kiểm tra model runtime trước khi xác nhận kết quả.",
            ),
            _record(
                "test-1",
                "test",
                "Mình cần kiểm tra model runtime trước khi xác nhận kết quả.!!!!!!!!",
            ),
        ),
        policy=SyntheticTextQualityPolicy(
            maximum_prefix_share=1.0,
            cross_split_similarity_threshold=0.99,
            forbidden_implementation_terms=frozenset({"model runtime"}),
        ),
    )

    assert not assessment.accepted
    assert assessment.cross_split_near_duplicate_count == 1
    assert assessment.implementation_term_count == 2
    assert sensitive_record_id not in "\n".join(assessment.errors)


def test_text_gate_cannot_be_evaded_with_punctuation_inside_words() -> None:
    assessment = assess_synthetic_text_quality(
        (
            _record(
                "train-1",
                "train",
                "Mình cần kiểm tra nguồn trước khi xác nhận kết quả.",
            ),
            _record(
                "test-1",
                "test",
                "M.ì.n.h c.ầ.n k.i.ể.m t.r.a n.g.u.ồ.n trước khi xác nhận kết quả.",
            ),
        ),
        policy=SyntheticTextQualityPolicy(
            maximum_prefix_share=1.0,
            cross_split_similarity_threshold=0.99,
        ),
    )

    assert not assessment.accepted
    assert assessment.cross_split_near_duplicate_count == 1


def test_text_gate_cannot_be_evaded_with_unique_prefix_padding() -> None:
    repeated_response = (
        "Mình sẽ hỏi lại một điểm để hiểu đúng nhu cầu rồi mới hỗ trợ. " * 12
    )
    assessment = assess_synthetic_text_quality(
        (
            _record(
                "train-1",
                "train",
                f"Cam quýt bưởi xoài na. {repeated_response}",
            ),
            _record(
                "test-1",
                "test",
                f"Sen cúc mai đào lan. {repeated_response}",
            ),
        ),
        policy=SyntheticTextQualityPolicy(
            maximum_prefix_share=1.0,
            cross_split_similarity_threshold=0.90,
        ),
    )

    assert not assessment.accepted
    assert assessment.cross_split_near_duplicate_count == 1


def test_text_gate_never_emits_candidate_controlled_identifiers() -> None:
    sensitive_marker = "private@example.com"
    malformed = _record("safe-record", "train", "Một câu trả lời an toàn.")
    malformed["record_id"] = sensitive_marker
    malformed["messages"] = "not-a-list"

    try:
        assess_synthetic_text_quality((malformed,))
    except ValueError as error:
        assert sensitive_marker not in str(error)
    else:
        raise AssertionError("malformed messages must fail closed")

    invalid_split = _record("safe-record", sensitive_marker, "Một câu trả lời.")
    try:
        assess_synthetic_text_quality((invalid_split,))
    except ValueError as error:
        assert sensitive_marker not in str(error)
    else:
        raise AssertionError("unknown split must fail closed")


def test_v4_generator_is_fail_closed_by_text_derived_quality_gate() -> None:
    candidate = build_v4_candidate(
        generator_source_sha256=(
            VIVI_BEHAVIOR_SYNTHETIC_V4_AUTHORITY.generator_source_sha256
        )
    )

    assessment = assess_synthetic_text_quality(candidate.records)

    assert assessment.record_count == 625
    assert assessment.split_counts == {
        "test": 125,
        "train": 400,
        "validation": 100,
    }
    assert not assessment.accepted
    assert assessment.maximum_prefix_share == {
        "test": 0.04,
        "train": 0.05,
        "validation": 0.05,
    }
    assert assessment.cross_split_near_duplicate_count > 0
    assert assessment.implementation_term_count == 5
