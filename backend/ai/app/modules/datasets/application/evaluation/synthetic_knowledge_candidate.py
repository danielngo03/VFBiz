"""Deterministic fact-free knowledge surfaces for ingestion qualification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final

DATASET_ID: Final[str] = "synthetic-document-ai-pilot-v1"
SCHEMA_REVISION: Final[str] = "synthetic-knowledge-candidate-v1"
GENERATOR_REVISION: Final[str] = "vfbiz-synthetic-knowledge-generator-v1"


@dataclass(frozen=True, slots=True)
class SyntheticDocument:
    document_id: str
    page_mode: str
    page_texts: tuple[str, ...]


_DOCUMENTS: Final[tuple[SyntheticDocument, ...]] = (
    SyntheticDocument(
        document_id="synthetic-native-text",
        page_mode="native-text",
        page_texts=(
            "Tài liệu minh họa mô tả cách xác nhận phạm vi câu hỏi trước khi tra cứu.",
            "Câu trả lời thử nghiệm phải nêu rõ khi chưa có nguồn đã được phát hành.",
            "Mỗi đoạn trích thử nghiệm giữ liên kết tới trang và bản nội dung bất biến.",
            "Nếu bằng chứng không đủ, trợ lý chuyển sang làm rõ hoặc bàn giao phù hợp.",
        ),
    ),
    SyntheticDocument(
        document_id="synthetic-image-only",
        page_mode="image-only",
        page_texts=(
            "Phiếu minh họa yêu cầu kiểm tra chất lượng trước khi lập chỉ mục tìm kiếm.",
            "Trang có độ tin cậy thấp phải đi vào hàng đợi xem xét thay vì tự phát hành.",
            "Nội dung trích xuất được xem là dữ liệu không tin cậy đối với chỉ dẫn hệ thống.",
            "Bản ghi thử nghiệm chỉ chứng minh luồng xử lý và không chứa thông tin sản phẩm.",
        ),
    ),
    SyntheticDocument(
        document_id="synthetic-mixed-page",
        page_mode="mixed-page",
        page_texts=(
            "Biểu mẫu minh họa kết hợp văn bản và hình ảnh trong cùng một hồ sơ thử nghiệm.",
            "Bộ xử lý phải giữ thứ tự trang khi ghép các phần nội dung đã chuẩn hóa.",
            "Trích dẫn thử nghiệm không được trỏ sang tài liệu hoặc revision khác.",
            "Việc kích hoạt kho tra cứu cần một quyết định độc lập ngoài gói dữ liệu này.",
        ),
    ),
)


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_jsonl(rows: tuple[dict[str, object], ...]) -> bytes:
    return b"".join(canonical_json(row) + b"\n" for row in rows)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def build_document_lock() -> dict[str, object]:
    return {
        "schema_revision": "synthetic-document-lock-v1",
        "dataset_id": DATASET_ID,
        "locked_before_render": True,
        "documents": [
            {
                "document_id": document.document_id,
                "page_mode": document.page_mode,
                "page_count": len(document.page_texts),
                "synthetic_source_sha256": _source_digest(document),
            }
            for document in _DOCUMENTS
        ],
    }


def render_knowledge_rows(*, document_lock_sha256: str) -> tuple[dict[str, object], ...]:
    """Render page-anchored surfaces without claiming provider OCR."""

    rows: list[dict[str, object]] = []
    for document in _DOCUMENTS:
        source_sha256 = _source_digest(document)
        for page_number, text in enumerate(document.page_texts, start=1):
            page_text_sha256 = sha256(text.encode("utf-8"))
            record_id = f"{document.document_id}:page-{page_number:03d}"
            rows.append(
                {
                    "record_id": record_id,
                    "family_id": document.document_id,
                    "document_id": document.document_id,
                    "text": text,
                    "page_start": page_number,
                    "page_end": page_number,
                    "page_text_sha256": page_text_sha256,
                    "source_sha256": source_sha256,
                    "citation": {
                        "document_id": document.document_id,
                        "page": page_number,
                        "source_sha256": source_sha256,
                    },
                    "lineage": {
                        "origin": "synthetic-qualification",
                        "page_mode": document.page_mode,
                        "extraction_method": "synthetic-fixture",
                        "cloud_ocr_performed": False,
                        "document_lock_sha256": document_lock_sha256,
                    },
                    "environment": "development",
                    "visibility": "developer-only",
                    "human_adjudicated": False,
                    "training_eligible": False,
                    "upload_allowed": False,
                    "release_eligible": False,
                }
            )
    return tuple(rows)


def _source_digest(document: SyntheticDocument) -> str:
    return sha256(
        canonical_json(
            {
                "authority": "fact-free-synthetic-qualification-source-v1",
                "document_id": document.document_id,
                "page_mode": document.page_mode,
                "page_texts": document.page_texts,
            }
        )
    )


__all__ = [
    "DATASET_ID",
    "GENERATOR_REVISION",
    "SCHEMA_REVISION",
    "build_document_lock",
    "canonical_json",
    "canonical_jsonl",
    "render_knowledge_rows",
    "sha256",
]
