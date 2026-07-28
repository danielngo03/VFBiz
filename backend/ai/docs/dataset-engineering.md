---
id: ai-dataset-engineering
title: Dataset Factory cho Customer Chatbot
status: active
owner_role: data-owner
scope: ai
when_to_read:
  - dataset-source
  - synthetic-dataset
  - dataset-release
  - ai-dataset
tags:
  - dataset
  - evaluation
  - synthetic-data
revision: 4
review_date: 2026-08-28
supersedes: []
---

# Dataset Factory cho Customer Chatbot

## Classification contract

Dataset dùng các chiều độc lập: `asset_kind`, `allowed_use`, `task_family`,
`modality`, `split_role`, `trust_zone` và `processing_stage`. `Multimodal` là
modality, không phải purpose; intent/OOD, tool, conversation, safety và state là
task family, không phải allowed use.

Mỗi release chỉ có một `allowed_use` chính: knowledge-index,
classifier-training, SFT, preference, embedding, reranker, evaluation hoặc
red-team. Một source có thể tạo nhiều artifact dẫn xuất với lineage riêng.
Golden, held-out test, evaluation-case và red-team bị fail-closed khỏi training,
knowledge index và synthetic seed.

## Source discovery

`dataset-source-researcher` chỉ tạo Source Register candidate cùng URL, revision,
checksum khi có, license evidence, access condition và proposed purpose. Role
này không download, accept license hoặc phát hành data. Missing/contradictory
rights có trạng thái `legal-hold` hoặc `rejected`.

Source lifecycle và artifact fetch là hai state machine độc lập:

```text
Source: candidate -> legal-hold | fetch-approved | rejected
        fetch-approved -> purpose-approved -> tombstoned
Fetch:  requested -> downloading -> quarantined -> verified
        -> scan-passed | rejected | deleted
```

`fetch-approved` chỉ cho tải exact revision từ allowlisted HTTPS origin vào
`quarantine`. Upstream checksum là optional; observed SHA-256 và tree hash chỉ
có thể được ghi sau fetch. `purpose-approved` mới cho phép transform hoặc đưa
vào candidate mixture và đòi rights, scan, retention, ACL cùng Data Owner evidence. Không thực thi remote
dataset script hoặc `trust_remote_code`; chỉ nhận JSON/JSONL/CSV/Parquet.

Dataset Card của nhà cung cấp là evidence tham khảo, không thay Legal/Data Owner.
Nội dung VinFast cần Content/Legal Owner cho phép trước crawl, index hoặc dùng
làm generation fact.

## Synthetic generation

`synthetic-dataset-builder` nhận generation job đã duyệt gồm schema, seed,
coverage matrix, approved synthetic facts, model/prompt/policy revision, budget,
shard lease và stop conditions. Builder chỉ ghi candidate shard riêng; không
được cập nhật registry/release hoặc dùng production PII/customer chat.

Candidate bao gồm tiếng Việt có dấu/không dấu, typo, slang, code-switch,
multi-turn, hard negative, contradiction, stale evidence, missing evidence,
tool error, interrupt và adversarial variants. Giá, promotion, policy hoặc
thông số không có source được duyệt phải dùng namespace/value synthetic rõ ràng.

## Quality gates

1. JSON Schema và enum/range validation.
2. Source grounding hoặc `synthetic_fact_namespace`.
3. Secret/PII/unsafe-rights/toxicity scan theo purpose.
4. Exact hash và semantic near-duplicate detection.
5. Split contamination và source-family leakage check.
6. Coverage theo intent, risk, locale, profile và failure mode.
7. Versioned LLM-as-a-Judge rubric; judge chỉ tạo evidence.
8. Human stratified review; 100% giá/safety/legal/PII/tool authorization.
9. Independent `dataset-quality-reviewer`.
10. Data Owner/Legal/Privacy decision và signed release manifest.

Generator không được review/release output của mình. Registry và release manifest
giữ exclusive lease; candidate shard có prefix/lease riêng.

## Quy mô đợt đầu

- 1.000 Golden cases được human adjudication đầy đủ và chỉ dùng evaluation.
- 10.000–30.000 synthetic candidates được tạo có budget và resumable shards.
- Chỉ subset vượt toàn bộ gate được release cho evaluation/red-team.
- Không tạo SFT release trong đợt đầu.

Số lượng candidate không phải KPI chất lượng. Stopping rule dựa trên coverage,
failure discovery, reviewer capacity và marginal value.

## Storage

- Git: schema, non-sensitive manifest và fixture nhỏ.
- `local-data/ai-datasets`: developer-only, gitignored.
- Object storage: `quarantine`, `candidate`, `released`,
  `restricted-evaluation`, `red-team`, `review-evidence`, `tombstones`.
- AI PostgreSQL: Source Register, lineage, approval, release và tombstone.

Dataset Registry runtime được tổ chức thành `domain`, `application` và
`infrastructure`. Domain sở hữu state transition và purpose separation;
application chỉ biết repository/object-store port; PostgreSQL và local
content-addressed storage là adapter. GCS production phải triển khai cùng key
contract và workload identity, không đưa service-account JSON vào repository.

Mỗi trust zone dùng bucket GCS riêng. Upload dùng content-addressed object key,
`ifGenerationMatch=0` và ADC/workload identity. Dataset Factory chỉ tạo và
upload artifact; không submit training job.

Artifact dùng content-addressed path; không có mutable `released/latest`.
PostgreSQL pointer trỏ tới immutable manifest digest. Golden/evaluation payload
chỉ ở `restricted-evaluation` và luôn có `allowed_use=evaluation`.

Candidate manifest luôn trỏ vào zone `candidate`. Chỉ activation đã được Data
Owner và Release Owner phê duyệt mới được tạo pointer immutable tới `released`,
`restricted-evaluation` hoặc `red-team`; việc đổi field `status` không tự di
chuyển hay phát hành object.

Không commit large JSONL/Parquet, image, downloaded binary, production data hoặc
customer conversation. Mọi artifact pin content hash và deletion method.

## ViVi transformation và Google Cloud export

```text
exact revision -> quarantine -> structural/malware/DLP scan
-> canonical record -> quality/language scoring
-> exact/MinHash/semantic dedup -> taxonomy mapping
-> held-out contamination check -> independent review -> immutable release
```

Canonical record giữ source revision, record hash, transformation IDs,
split-family ID và contamination fingerprint. Public corpus không được tạo
factual VinFast answer. Tool data phải dùng JSON Schema VFBiz và có các case
unauthorized, missing argument, stale data và anomaly.

Google export profile tạo Gemini SFT/preference JSONL, Vertex embedding
`corpus.jsonl`, `queries.jsonl`, split TSV và evaluation JSONL. Export không
đổi allowed use, không trộn split family và không tự submit training.

## Public source candidate

Candidate register chỉ phục vụ research. Không download cho tới khi entry có
fetch approval, rồi purpose approval, rights, access condition, Data Owner và retention. License
mâu thuẫn hoặc non-commercial/no-derivatives bị quarantine/reject theo policy.

## Trạng thái vận hành

| Capability | Status |
| --- | --- |
| Contract và deterministic validation | Implemented foundation |
| Public source candidate research | Candidate / legal-hold |
| Dataset Registry state machine và PostgreSQL schema | Implemented foundation |
| Local content-addressed storage adapter | Implemented development adapter |
| GCS trust-zone adapter | Candidate; immutable upload/workload-token contract đã có |
| Wave A portfolio pin exact revision | Implemented |
| MASSIVE/XQuAD/Belebele smoke fetch | Quarantined local; chưa purpose-approved |
| Google Cloud export profile | Candidate; format validators đã có |
| First-party VinFast release | Human-blocked |
| Golden v1 1.000 case | Human-blocked; hiện 0 adjudicated |
| Synthetic 10.000–30.000 candidate | Target-only |
| Fine-tuning dataset | Ngoài baseline |
