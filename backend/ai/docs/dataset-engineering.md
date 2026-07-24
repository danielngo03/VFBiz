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
revision: 1
review_date: 2026-08-23
supersedes: []
---

# Dataset Factory cho Customer Chatbot

## Portfolio và purpose separation

Dataset được tách theo purpose: knowledge, retrieval evaluation, intent/OOD,
conversation quality, tool evaluation, refusal/safety, red-team,
state/resilience và multimodal. Một record không tự động được dùng cho knowledge,
evaluation và training. Held-out evaluation split được khóa trước mọi training
candidate.

## Source discovery

`dataset-source-researcher` chỉ tạo Source Register candidate cùng URL, revision,
checksum khi có, license evidence, access condition và proposed purpose. Role
này không download, accept license hoặc phát hành data. Missing/contradictory
rights có trạng thái `legal-hold` hoặc `rejected`.

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

- 500–1.000 gold cases được human review đầy đủ.
- 10.000–30.000 synthetic candidates được tạo có budget và resumable shards.
- Chỉ subset vượt toàn bộ gate được release cho evaluation/red-team.
- Không tạo SFT release trong đợt đầu.

Số lượng candidate không phải KPI chất lượng. Stopping rule dựa trên coverage,
failure discovery, reviewer capacity và marginal value.

## Storage

- Git: schema, non-sensitive manifest và fixture nhỏ.
- `local-data/ai-datasets`: developer-only, gitignored.
- Object storage: `quarantine`, `candidate`, `released`,
  `restricted-evaluation`, `red-team`.
- AI PostgreSQL: Source Register, lineage, approval, release và tombstone.

Không commit large JSONL/Parquet, image, downloaded binary, production data hoặc
customer conversation. Mọi artifact pin content hash và deletion method.

## Public source candidate

Candidate register chỉ phục vụ research. Không download cho tới khi entry có
approved purpose, rights, access condition, data owner và retention. License
mâu thuẫn hoặc non-commercial/no-derivatives bị quarantine/reject theo policy.
