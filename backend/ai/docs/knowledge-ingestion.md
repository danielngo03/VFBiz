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
revision: 9
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
  -> generation-pinned GCS object
  -> bounded Google Document AI batch
  -> reconciled provider output
  -> deterministic page normalization
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

Local bootstrap chỉ tạo immutable receipt và quarantine object. Nó không parse,
OCR, chunk hoặc embed PDF trên máy developer. PDF cần xử lý được chuyển qua
GCS/Pub/Sub tới pinned Google Document AI processor bằng workload identity;
thiếu cloud authority, page budget, exact generation hoặc processor revision thì
giữ trạng thái `awaiting-gcp-document-ai` hoặc `failed-safely`, không fallback
sang Tesseract hay parser OCR local.

Legacy derived artifacts tạo bởi pipeline cũ không được coi là knowledge
candidate. Chúng chỉ được inventory content-free (source/pipeline digest, page
count, byte count, extraction/disposition counts và tree digest) trong review
evidence với quyền `0700/0600`. Inventory không đọc raw text vào báo cáo, không
xóa artifact và không làm artifact visible cho active retriever. Tombstone/trash
chỉ chạy qua một operation riêng có lineage và rollback evidence.

Lệnh inventory chuẩn:

```sh
PYTHONPATH=. uv run --directory backend/ai python -m scripts.inventory_legacy_derived \
  --root /workspace/local-data/ai-datasets/derived-quarantine \
  --output /workspace/local-data/ai-datasets/review-evidence/legacy-derived-tesseract/inventory.json
```

Lệnh này chỉ tạo báo cáo; không có cờ xóa và không được dùng làm bằng chứng
cho việc materialize hoặc release.

Document AI không được coi là chính xác tuyệt đối. Mỗi page/output vẫn giữ
confidence, warning và source/page anchor; output dưới quality threshold hoặc
không qua PII/secret/prompt-injection scan đi `review-required` và không được
chunk/embed.

Downstream `DocumentAiCandidateMaterializer` chỉ nhận `DocumentAiExtractionResult`
đã có đầy đủ page lineage. Nó pin scanner/policy/chunker/embedding revisions,
đưa từng page lỗi vào review và chỉ gọi candidate sink sau khi toàn bộ tài liệu
đã pass scan, chunk và embedding lineage. Chỉ một page cần review cũng giữ cả
tài liệu ở `review-required`; không có partial document nào được xem là
`candidate-ready`.

Candidate sink receipts persist the source generation/metageneration, Document
AI processor revision, scanner/policy revisions and chunker/embedding
revisions alongside the extraction digest. A downstream reader can therefore
revalidate the complete authority chain without inferring revisions from file
names or filesystem timestamps.

Reconciliation dùng claim 300 giây, owner token và fencing token trong
PostgreSQL. Một job chỉ được một worker đọc output tại một thời điểm; claim hết
hạn mới được worker khác tiếp quản. Mọi evidence write phải mang đúng owner và
fence đã claim; writer cũ bị từ chối ngay khi fence mới tồn tại. Owner hiện tại
được ghi typed deadline failure sau lease expiry chỉ khi job chưa bị reclaim.
Provider observation, failure/backoff và
extraction evidence đều content-free. Permanent output failure đi
`quarantined`; transient failure retry sau 30/60 giây và lần thứ ba đi
`quarantined`. Batch tiếp tục các job khác thay vì để một poison object chặn
hàng đợi.

Output reader có global deadline 180 giây, nằm bên trong claim/HTTP envelope
300 giây, và hard-cap 20 JSON output objects cho mỗi reconciliation. Timeout
của từng provider call không vượt thời gian monotonic còn lại; deadline được
kiểm trước/sau provider call, trên từng streamed chunk, sau JSON decode/page
normalization/sort và trước khi trả kết quả cuối. HTTP 2xx nhưng JSON malformed
cũng trở thành typed content-free failure; raw response và parser exception
không vào evidence hoặc log.

Extraction evidence dùng `confidence_micros` dạng số nguyên thay vì JSON float,
để Python/PostgreSQL có cùng canonical digest. Trigger yêu cầu exact key set,
exact submitted GCS output prefix và đủ page 1..N; raw OCR/provider fields không
thể được nhét vào evidence. Worker staging input nằm trong `derived-dev`, còn
raw Document AI JSON chỉ nằm trong bucket `ocr-output-dev` dành riêng cho
reconciler; bucket này là ranh giới để quyền `storage.objects.list` không mở
ra staging data. Cả hai bucket mặc định có soft-delete bảy ngày; live object
expiry bảy ngày và noncurrent expiry một ngày chỉ bật cùng cờ IaC
`enable_derived_output_expiry` sau quyết định retention của Data Owner. Raw
OCR không vào PostgreSQL/API/log và thay đổi retention production vẫn cần
Data Owner quyết định riêng.

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
- PDF lớn nằm trong object storage và được chia thành batch tối đa theo provider
  page limit. Worker không tải toàn bộ binary hoặc toàn bộ derived text vào RAM;
  reconciliation xử lý output theo object/page có generation và digest pin.
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

- `synthetic-local`: packaged synthetic UTF-8 fixture nhỏ, deterministic
  scanner/chunker/embedder; dùng cho CI, không nhận PDF và không có OCR
  implementation.
- `gcp-document-ai`: GCS, Pub/Sub, Document AI OCR và managed embedding; chỉ bật
  sau khi typed config, workload identity, retention, quota và provider-outage
  tests đã đạt.

Candidate manifest pin source snapshot, code/policy/parser/chunker/scanner và
embedding revision. Manifest chỉ tham chiếu artifact đã commit bằng fence hiện
hành, chứa checkpoint và chuỗi parent checksum từ source → parsed unit → chunk
→ embedding. Ingestion không ghi vào bảng chunk active; VFBIZ-0025 sở hữu bước
materialize/activate retrieval snapshot.

## Private database bootstrap

Cloud ingestion dùng ba database identity tách biệt. Administrator URL chỉ đi
vào một phiên bản Secret Manager được pin cho Cloud Run bootstrap Job; submitter
và reconciler nhận hai URL/role khác nhau. Bootstrap image tách khỏi worker
image, chạy non-root, không có scheduler hoặc public invoker và phải pin digest.

Job nâng database đến Alembic head trước, sau đó migration
`20260802_0025_document_ai_database_bootstrap_epoch.py` ghi một singleton epoch,
claim UUID, authority digest và fencing token trong transaction. Chỉ claim đầu
tiên được tiếp tục; replay và concurrent execution bị từ chối trước khi tạo mật
khẩu hoặc secret version. Kết quả chuyển đúng một lần từ `reserved` sang
`completed` hoặc `failed`; UPDATE tiếp theo, DELETE và TRUNCATE bị trigger chặn.
Rotation về sau phải là workflow/version riêng, không chạy lại bootstrap.

Nếu provision thất bại, operator cố disable mọi secret version đã tạo và giữ
lỗi ban đầu; database chỉ ghi failure code không chứa credential. OpenTofu chỉ
tạo secret container/IAM/job, không tạo SQL user, password hoặc secret payload.
Foundation và bootstrap đều mặc định tắt; bật foundation không tự tạo hoặc chạy
bootstrap, worker, reconciliation, dispatch hay OCR.
