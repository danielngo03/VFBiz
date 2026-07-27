---
id: ai-knowledge-data-governance
title: Knowledge và dataset governance của AI Platform
status: active
owner_role: data-owner
scope: ai
when_to_read:
  - dataset
  - data-governance
  - ai-dataset
  - ai-retrieval
tags:
  - dataset
  - rag
  - retrieval
  - governance
revision: 2026-07-23.2
review_date: 2026-08-23
supersedes: []
---

# Knowledge và dataset governance

## Ownership boundary

AI Knowledge & Data triển khai source lifecycle, parsing/chunking, embedding,
ACL-aware retrieval và tombstone. Data Owner quyết định permitted purpose,
classification và release của dataset; Privacy/Legal tham gia khi có PII,
restricted data hoặc quyền sử dụng chưa rõ. API Platform vẫn giữ customer
identity/authorization; AI không tự suy quyền từ nội dung tài liệu.

## Ba loại dataset

| Loại | Mục đích | Bất biến |
| --- | --- | --- |
| Knowledge | Grounded RAG cho một assistant profile | Source/revision/freshness/citation và ACL namespace bắt buộc |
| Evaluation | Held-out regression và quality/safety measurement | Không xuất hiện trong retrieval/training candidate; có suite revision |
| Red-team | Injection, poisoning, exfiltration và abuse test | Restricted access; không index vào customer knowledge |

Một source không tự động được dùng cho cả ba mục đích. Mỗi use phải có purpose,
owner và approval evidence riêng để tránh contamination và purpose creep.

Dataset Factory hiện phân biệt thêm retrieval evaluation, intent/OOD,
conversation quality, tool evaluation, refusal/safety, state/resilience và
multimodal. `dataset-engineering.md` sở hữu generation/quality workflow; tài
liệu này vẫn là nguồn chuẩn về authority, purpose, ACL và lifecycle.

## Lifecycle bắt buộc

```text
register source -> quarantine -> malware/secret/PII/rights checks
-> classify and approve purpose -> parse/chunk/version -> embed
-> ACL namespace -> candidate evaluation -> human decision
-> immutable publish -> monitor freshness -> tombstone/delete
```

- Source register pin provenance, commercial-use rights, checksum, custodian,
  classification, retention, deletion method và effective revision.
- Chunk giữ source locator/revision; transform không được làm thay đổi factual
  meaning. Embedding revision/dimension phải explicit và không trộn âm thầm.
- ACL lọc trước ranking và được kiểm tra lại trước response. Public,
  customer-scoped và employee namespace/cache key tách biệt.
- Delete hoặc withdraw source phải tạo tombstone, loại chunk/vector/cache liên
  quan và để lại audit evidence; không chỉ ẩn UI.
- Dataset release không đồng nghĩa model/prompt/retriever/tool release.

Machine-readable contract nằm trong `contracts/ai/`. Public source candidate tại
`dataset-specs/public-source-candidates.json` chỉ là research metadata; entry
không ở trạng thái `approved` phải bị download gate từ chối trước network access.

## Storage và dữ liệu cấm

Source binary nằm trong object storage quarantine/private bucket; Git chỉ giữ
schema, synthetic fixture và manifest không nhạy cảm. AI PostgreSQL/pgvector giữ
metadata, redacted chunks, ACL, embeddings và release/evaluation references.
Không ghi secret, raw PII, customer conversation, provider payload hoặc private
binary vào Git, logs, prompts hay analytics.

"Redacted chunks" là một transform thật, không phải field name aspirational:
`CandidateMaterializationService` chạy `TextRedactor`
(`PatternBasedTextRedactor`) trên mọi chunk text trước khi ghi `redacted_text`,
phát hiện và mask email (đa domain-label), số điện thoại di động Việt Nam, VIN
và địa chỉ (từ khóa đường/phố tiếng Việt lẫn street/road tiếng Anh, nhánh
admin-unit yêu cầu từ theo sau viết hoa để tránh redact nhầm cụm từ thường như
"thành phố thông minh"). Tên người: họ Việt Nam phổ biến (case-insensitive,
bắt được cả bản ALL-CAPS) hoặc honorific tiếng Anh (Mr/Mrs/Ms/Miss/Dr) + từ
viết hoa theo sau — tên tiếng Anh KHÔNG có honorific chưa được bắt, đây là gap
đã biết chứ không phải "tiếng Việt/Anh" đầy đủ. Rule-based heuristic có
false-negative đã biết (họ hiếm không nằm trong danh sách, tên tiếng Anh trần
trụi, địa chỉ viết không theo mẫu, số điện thoại cố định 02x chưa bắt), thiên
về over-redact hơn là bỏ sót — chưa phải compliance-certified scrubber; Privacy
Owner review độ đầy đủ category (đặc biệt coverage tiếng Anh) trước khi bật
nguồn ingestion thật.

## Handoff và decision

Implementer tạo immutable candidate/evidence rồi chuyển cho đúng human owner.
Thiếu provenance, license, data owner, ACL, retention hoặc deletion evidence là
`failed-safely`; không tạo placeholder approval. Bất đồng về product purpose về
PO, data use về Data Owner, PII về Privacy Owner và rights về Legal Owner.
