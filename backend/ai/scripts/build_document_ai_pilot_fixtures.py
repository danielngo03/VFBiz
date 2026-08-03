"""Build deterministic, fact-free PDF fixtures for the Document AI pilot.

The generated PDFs are development-only input artifacts. They contain no
VinFast facts, customer data, approval claims, training examples or release
authority. Output belongs under ignored ``local-data`` and must not enter Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw, ImageFont
from PIL import __version__ as pillow_version
from reportlab import Version as reportlab_version
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

GENERATOR_REVISION: Final = "document-ai-pilot-fixture-v1"
DEFAULT_FONT: Final = Path.home() / "Library/Fonts/DejaVuSans.ttf"
APPROVED_FONT_SHA256: Final = "7da195a74c55bef988d0d48f9508bd5d849425c1770dba5d7bfc6ce9ed848954"
FONT_LICENSE_SHA256: Final = "7a083b136e64d064794c3419751e5c7dd10d2f64c108fe5ba161eae5e5958a93"
FONT_SOURCE_URL: Final = (
    "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/"
    "version_2_37/dejavu-sans-ttf-2.37.zip"
)
PAGE_WIDTH, PAGE_HEIGHT = A4


@dataclass(frozen=True)
class FixtureSpec:
    name: str
    mode: str
    pages: tuple[tuple[str, ...], ...]


FIXTURES: Final = (
    FixtureSpec(
        name="native-text",
        mode="native-text",
        pages=(
            (
                "TÀI LIỆU KIỂM THỬ TRÍCH XUẤT VĂN BẢN",
                "Nội dung này hoàn toàn tổng hợp và không chứa thông tin sản phẩm.",
                "Trợ lý cần hỏi lại khi yêu cầu chưa rõ và không được tự đoán dữ kiện.",
            ),
            (
                "TRANG THỨ HAI — KIỂM THỬ DẤU TIẾNG VIỆT",
                "Nếu chưa có nguồn đã duyệt, trợ lý phải từ chối hoặc chuyển chuyên viên.",
                "Mọi câu trả lời có dữ kiện phải kèm trích dẫn và phiên bản tài liệu.",
            ),
        ),
    ),
    FixtureSpec(
        name="image-only",
        mode="image-only",
        pages=(
            (
                "TÀI LIỆU ẢNH TỔNG HỢP",
                "Trang này chỉ chứa ảnh để kiểm thử OCR tiếng Việt.",
                "Không có dữ liệu khách hàng, giá, chính sách hoặc thông số xe.",
            ),
            (
                "KIỂM THỬ OCR TRANG HAI",
                "Kết quả độ tin cậy thấp phải chuyển sang hàng đợi xem xét thủ công.",
                "Hệ thống không được tuyên bố OCR chính xác tuyệt đối.",
            ),
        ),
    ),
    FixtureSpec(
        name="mixed-page",
        mode="mixed-page",
        pages=(
            (
                "TRANG VĂN BẢN TRONG TÀI LIỆU HỖN HỢP",
                "Trang đầu dùng lớp văn bản gốc để kiểm thử native extraction.",
                "Nội dung tổng hợp chỉ chứng minh luồng kỹ thuật.",
            ),
            (
                "TRANG ẢNH TRONG TÀI LIỆU HỖN HỢP",
                "Trang sau dùng ảnh để kích hoạt OCR theo từng trang.",
                "Tài liệu này không đủ điều kiện training hoặc phát hành.",
            ),
        ),
    ),
)


def expected_relative_paths() -> set[str]:
    return {
        ".",
        "checksums.sha256",
        "manifest.json",
        "pdfs",
        *(f"pdfs/{spec.name}.pdf" for spec in FIXTURES),
    }


def verify_output_tree(output_root: Path, *, require_complete: bool) -> None:
    if output_root.is_symlink():
        raise ValueError("output root must not be a symlink")
    if not output_root.exists():
        return
    if not output_root.is_dir():
        raise ValueError("output root must be a directory")

    observed = {"."}
    for candidate in output_root.rglob("*"):
        relative_path = candidate.relative_to(output_root).as_posix()
        metadata = candidate.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"output tree contains a symlink: {relative_path}")
        if stat.S_ISDIR(metadata.st_mode):
            observed.add(relative_path)
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError(f"output tree contains a non-regular or linked file: {relative_path}")
        observed.add(relative_path)

    expected = expected_relative_paths()
    unexpected = observed - expected
    if unexpected:
        raise ValueError(f"output tree contains unexpected paths: {sorted(unexpected)}")
    if require_complete and observed != expected:
        raise ValueError(f"output tree is incomplete: {sorted(expected - observed)}")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: object) -> bytes:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{serialized}\n".encode()


def draw_native_page(canvas: Canvas, lines: tuple[str, ...], *, page_number: int) -> None:
    canvas.setFont("PilotUnicode", 17)
    canvas.drawString(54, PAGE_HEIGHT - 72, lines[0])
    canvas.setFont("PilotUnicode", 12)
    y = PAGE_HEIGHT - 118
    for line in lines[1:]:
        canvas.drawString(54, y, line)
        y -= 28
    canvas.setFont("PilotUnicode", 9)
    canvas.drawString(54, 42, f"synthetic-document-ai-pilot-v1 · trang {page_number}")


def image_page(lines: tuple[str, ...], *, font_path: Path, page_number: int) -> Image.Image:
    width, height = 1240, 1754
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    heading = ImageFont.truetype(str(font_path), 38)
    body = ImageFont.truetype(str(font_path), 27)
    footer = ImageFont.truetype(str(font_path), 19)
    draw.text((100, 130), lines[0], fill="black", font=heading)
    y = 250
    for line in lines[1:]:
        draw.text((100, y), line, fill="black", font=body)
        y += 72
    draw.text(
        (100, height - 100),
        f"synthetic-document-ai-pilot-v1 · trang {page_number}",
        fill="black",
        font=footer,
    )
    return image


def build_pdf(path: Path, spec: FixtureSpec, *, font_path: Path) -> None:
    canvas = Canvas(
        str(path),
        pagesize=A4,
        pageCompression=1,
        invariant=1,
        pdfVersion=(1, 7),
    )
    canvas.setAuthor("VFBiz synthetic fixture generator")
    canvas.setCreator(GENERATOR_REVISION)
    canvas.setSubject("Fact-free Document AI pipeline qualification")
    canvas.setTitle(f"VFBiz {spec.name} synthetic fixture")
    for index, lines in enumerate(spec.pages, start=1):
        use_image = spec.mode == "image-only" or (spec.mode == "mixed-page" and index == 2)
        if use_image:
            image = image_page(lines, font_path=font_path, page_number=index)
            canvas.drawImage(
                ImageReader(image),
                0,
                0,
                width=PAGE_WIDTH,
                height=PAGE_HEIGHT,
                preserveAspectRatio=False,
                mask=None,
            )
        else:
            draw_native_page(canvas, lines, page_number=index)
        canvas.showPage()
    canvas.save()


def atomic_write(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build(output_root: Path, *, font_path: Path) -> dict[str, object]:
    if not font_path.is_file() or font_path.is_symlink():
        raise ValueError("font path must be one existing regular non-symlink file")
    font_sha256 = sha256_bytes(font_path.read_bytes())
    if font_sha256 != APPROVED_FONT_SHA256:
        raise ValueError("font bytes do not match the approved open-license DejaVu Sans 2.37")
    verify_output_tree(output_root, require_complete=False)
    output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output_root, 0o700)
    pdf_root = output_root / "pdfs"
    pdf_root.mkdir(mode=0o700, exist_ok=True)
    os.chmod(pdf_root, 0o700)
    pdfmetrics.registerFont(TTFont("PilotUnicode", str(font_path)))

    records: list[dict[str, object]] = []
    for spec in FIXTURES:
        with tempfile.NamedTemporaryFile(suffix=".pdf", dir=pdf_root, delete=False) as handle:
            temporary = Path(handle.name)
        final_path = pdf_root / f"{spec.name}.pdf"
        try:
            build_pdf(temporary, spec, font_path=font_path)
            content = temporary.read_bytes()
            if not content.startswith(b"%PDF-1.7") or not content.rstrip().endswith(b"%%EOF"):
                raise ValueError(f"generated file is not a bounded PDF 1.7: {spec.name}")
            atomic_write(final_path, content)
        finally:
            temporary.unlink(missing_ok=True)
        records.append(
            {
                "bytes": final_path.stat().st_size,
                "mode": spec.mode,
                "page_count": len(spec.pages),
                "relative_path": f"pdfs/{final_path.name}",
                "sha256": sha256_bytes(final_path.read_bytes()),
            }
        )

    manifest_without_digest: dict[str, object] = {
        "allowed_use": "document-ai-ingestion-qualification-only",
        "cloud_ocr_performed": False,
        "dataset_id": "synthetic-document-ai-pilot-v1",
        "environment": "development",
        "fixtures": records,
        "font_license_id": "LicenseRef-DejaVu-Fonts-2.37",
        "font_license_sha256": FONT_LICENSE_SHA256,
        "font_sha256": font_sha256,
        "font_source_url": FONT_SOURCE_URL,
        "generator_revision": GENERATOR_REVISION,
        "human_adjudicated": False,
        "pillow_revision": pillow_version,
        "release_eligible": False,
        "reportlab_revision": reportlab_version,
        "schema_revision": "document-ai-pilot-fixture-manifest-v1",
        "training_eligible": False,
        "upload_allowed": False,
        "visibility": "developer-only",
    }
    manifest = {
        **manifest_without_digest,
        "manifest_digest": sha256_bytes(canonical_json(manifest_without_digest)),
    }
    atomic_write(output_root / "manifest.json", canonical_json(manifest))
    checksums = "".join(f"{item['sha256']}  {item['relative_path']}\n" for item in records).encode()
    atomic_write(output_root / "checksums.sha256", checksums)
    verify_output_tree(output_root, require_complete=True)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--font", type=Path, default=DEFAULT_FONT)
    args = parser.parse_args()
    output = Path(os.path.abspath(args.output))
    font = Path(os.path.abspath(args.font))
    manifest = build(output, font_path=font)
    print(json.dumps({"manifest_digest": manifest["manifest_digest"]}, sort_keys=True))


if __name__ == "__main__":
    main()
