---
id: ai-knowledge-ingestion
title: Knowledge-source ingestion của AI Platform
status: active
owner_role: data-owner
scope: ai
when_to_read:
  - dataset-source
  - knowledge-ingestion
  - ai-retrieval
tags:
  - knowledge
  - ingestion
  - retrieval
  - data-governance
revision: 4
review_date: 2026-08-23
supersedes: []
---

# Boundary

Knowledge-source ingestion biến một source đã được phê duyệt thành candidate
knowledge artifact. Nó không tự duyệt rights, không tự activate Knowledge
Release và không tạo training/evaluation dataset từ cùng record.

`dataset-engineering.md` quản lý evaluation/red-team/synthetic dataset.
Tài liệu này chỉ quản lý runtime knowledge cho RAG.

## Entry gate

Trước network access, Source Register v2 phải có:

- `status=approved`, checksum và pinned source revision;
- `approved_purposes` chứa `knowledge`;
- `acl_namespaces` đúng assistant profile/domain/locale;
- owner, custodian, classification, retention và deletion method;
- Legal/Data approval evidence cùng commercial/derivative-use rights phù hợp.

Thiếu một trường thì job trả `failed-safely`; worker không tự sửa metadata hoặc
hạ classification.

## Pipeline

```text
approved source
  -> approved-source adapter
  -> quarantine object
  -> checksum/signature/MIME/size verification
  -> pre-parse object safety scan
  -> deterministic parse
  -> post-parse PII/secret/injection scan
  -> versioned chunk
  -> embedding port
  -> candidate namespace
  -> lineage/quality evidence
```

Mỗi stage có durable checkpoint và được xử lý trong một lease riêng. Job pin
source, parser, chunker, scanner, embedding model/dimension, ACL, policy và code
revision. PostgreSQL dùng optimistic version, fencing token và `SKIP LOCKED`;
worker heartbeat gia hạn lease bằng cùng version/fencing token và worker hết
lease không thể commit kết quả. Parser tiếp tục bằng opaque byte cursor; scan,
parse, chunk và embed chỉ xử lý một bounded unit trong mỗi claim. Partial
artifact chỉ nằm trong candidate namespace và không được active retriever nhìn
thấy.

Baseline staging chỉ bật packaged synthetic UTF-8 Markdown adapter, không có
network. PDF, archive, image và OCR bị từ chối theo signature cho tới khi có
sandboxed parser profile, provider owner, resource ceiling và acceptance test
tương ứng. Đây là fail-closed boundary, không phải tuyên bố đã xử lý PDF an toàn.

## Fetch và quarantine

- Production network adapter phải có egress allowlist theo host/scheme; redirect
  target phải được kiểm lại. Baseline adapter chỉ ánh xạ opaque source ID/revision
  tới fixture nằm dưới một root allowlisted, không nhận path hoặc URL từ request.
- Giới hạn byte/time/content type; archive bomb và path traversal bị chặn.
- Provider credential chỉ từ workload identity/secret manager.
- Original binary ở quarantine/private object storage, không ở Git hoặc
  PostgreSQL row.

## Parse, chunk và embedding có giới hạn tài nguyên

- Parser theo allowlisted MIME/schema; unsupported content bị quarantine.
- HTTP/API process không parse hoặc OCR source. Worker pool lấy job từ queue và
  xử lý theo page/chunk; mỗi worker có byte/page/pixel/time/memory ceiling.
- PDF lớn được stream từ object storage, không load toàn bộ binary hoặc toàn bộ
  derived text vào RAM. OCR/render tạo artifact theo page và giải phóng resource
  trước page kế tiếp.
- Archive/document lồng nhau có maximum expansion ratio, recursion depth và
  extracted-file count. Image có decoded-pixel ceiling độc lập file size.
- Chunk ID deterministic từ source revision + location + normalized content.
- Exact/semantic duplicate giữ lineage, không âm thầm xóa source attribution.
- Embedding nằm sau ACL metadata; dimension/model mismatch không được upsert.
- Object scan chạy trước parser; PII/secret/prompt injection scan chạy trên text
  đã parse trước chunk/embed. `rejected` hoặc `indeterminate` đều fail closed.
  Scan này là reject-only (`DeterministicContentScanner`), không transform nội
  dung. Redaction thật (mask/replace PII) là một gate riêng, chạy sau, ở bước
  materialization (candidate -> `redacted_text`) — xem
  `knowledge-data-governance.md`.

## Deletion và tombstone

Source tombstone hoặc DSAR tạo deletion job theo lineage: original object,
derived text, chunk, embedding, cache và evaluation trace liên quan. Evidence
chỉ giữ opaque ID/hash hợp pháp, không sao chép nội dung đã xóa.

## Failure, resume và DLQ

Retry chỉ cho lỗi transient có bounded backoff. Checksum/rights/PII/schema lỗi
không retry tự động. Stage checkpoint pin artifact checksum và last completed
page/chunk để resume không parse lại phần đã xác nhận. Worker crash hoặc timeout
không làm candidate visible.

Job vượt attempt limit chuyển trạng thái `dead_lettered` với job/source/revision ID, failed stage,
typed reason, attempt history và artifact locator đã minimize. DLQ replay cần
operator capability, active Source Register approval và idempotency key; không
được đổi parser/policy revision ngầm trong cùng job. DLQ có retention/deletion
lineage và không lưu raw document trong queue payload.

Telemetry fire-and-forget, redacted và không làm chết main job. Metrics gồm
stage latency, peak memory, page/byte/record count, retry/DLQ rate, duplicate
rate, scan failure, embedding cost và deletion lag.

## Required tests

- Source thiếu rights/purpose/ACL bị chặn trước network.
- Redirect/MIME/size/checksum và archive bomb bị từ chối.
- PDF lớn/ảnh lớn giữ memory ceiling; worker timeout có thể resume từ stage/page
  đã checkpoint.
- Resume không tạo chunk/embedding trùng.
- Permanent failure không retry; DLQ replay yêu cầu authority và không đổi
  revision/policy ngầm.
- Candidate không xuất hiện trong active retriever.
- Tombstone xóa đủ lineage và cache.
- Evaluation/training split không nhận runtime knowledge record ngoài workflow
  riêng.

## Adapter profiles

`application/` chỉ định nghĩa aggregate, use case, runner và port. PostgreSQL,
object storage, scanner, parser và embedding là adapter thay thế được trong
`infrastructure/`; tên provider không trở thành top-level module.

- `synthetic-local`: fixture UTF-8 nhỏ, deterministic scanner/chunker/embedder;
  dùng cho CI và local staging, không được dùng như production knowledge source.
- `gcp-production`: GCS, Pub/Sub, Document AI/OCR và managed embedding; chỉ bật
  sau khi typed config, workload identity, retention, quota và provider-outage
  tests đã đạt.

Candidate manifest pin source snapshot, code/policy/parser/chunker/scanner và
embedding revision. Manifest chỉ tham chiếu artifact đã commit bằng fence hiện
hành, chứa checkpoint và chuỗi parent checksum từ source → parsed unit → chunk
→ embedding. Ingestion không ghi vào bảng chunk active; VFBIZ-0025 sở hữu bước
materialize/activate retrieval snapshot.
