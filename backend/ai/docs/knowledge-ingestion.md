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
revision: 1
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
  -> allowlisted fetch
  -> quarantine object
  -> checksum/MIME/size/redirect verification
  -> malware/secret/PII/rights scan
  -> deterministic parse
  -> versioned chunk
  -> embedding port
  -> candidate namespace
  -> lineage/quality evidence
```

Mỗi stage idempotent và resumable. Job pin source, parser, chunker, embedding
model/dimension, ACL, policy và code revision. Partial artifact không được
visible qua active retriever.

## Fetch và quarantine

- Egress allowlist theo host/scheme; redirect target phải được kiểm lại.
- Giới hạn byte/time/content type; archive bomb và path traversal bị chặn.
- Provider credential chỉ từ workload identity/secret manager.
- Original binary ở quarantine/private object storage, không ở Git hoặc
  PostgreSQL row.

## Parse, chunk và embedding

- Parser theo allowlisted MIME/schema; unsupported content bị quarantine.
- Chunk ID deterministic từ source revision + location + normalized content.
- Exact/semantic duplicate giữ lineage, không âm thầm xóa source attribution.
- Embedding nằm sau ACL metadata; dimension/model mismatch không được upsert.
- PII/secret/prompt injection observation đi cùng chunk evidence để policy có
  thể reject trước activation.

## Deletion và tombstone

Source tombstone hoặc DSAR tạo deletion job theo lineage: original object,
derived text, chunk, embedding, cache và evaluation trace liên quan. Evidence
chỉ giữ opaque ID/hash hợp pháp, không sao chép nội dung đã xóa.

## Failure và observability

Retry chỉ cho lỗi transient có bounded backoff. Checksum/rights/PII/schema lỗi
không retry tự động. Telemetry fire-and-forget, redacted và không làm chết main
job. Metrics gồm stage latency, byte/record count, duplicate rate, scan failure,
embedding cost và deletion lag.

## Required tests

- Source thiếu rights/purpose/ACL bị chặn trước network.
- Redirect/MIME/size/checksum và archive bomb bị từ chối.
- Resume không tạo chunk/embedding trùng.
- Candidate không xuất hiện trong active retriever.
- Tombstone xóa đủ lineage và cache.
- Evaluation/training split không nhận runtime knowledge record ngoài workflow
  riêng.
