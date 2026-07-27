---
id: VFBIZ-0100
title: First governed business Knowledge Release
status: proposed
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/docs/knowledge-release.md
  - backend/ai/tests/evaluation/knowledge
  - guides/customer-ai
  - docs/work/plans/customer-chatbot-runtime-sequence.md
depends_on:
  - VFBIZ-0025
controlled_signals:
  - knowledge-release
  - data-governance
  - license
  - pii
  - ai-release
exclusive_resources:
  - ai-knowledge-release-registry
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 1
review_date: "2026-07-25"
---

# Outcome

Một VinFast business knowledge source có provenance/rights hợp lệ được
independent-evaluate và human approve, sau đó activate atomically thành release
đầu tiên mà runtime có thể truy xuất; nếu chưa có nguồn hợp lệ, work item phải
giữ `blocked` thay vì dùng synthetic fact.

## Constraints

- Data/Legal/Privacy/Release authority là human và phải khác ingestion builder.
- Không crawl, download, index hoặc upload nội dung VinFast khi thiếu source
  owner, permitted purpose, rights evidence, checksum và retention policy.
- Không copy credential, signed URL, customer PII hoặc restricted document vào
  Git/evidence.
- Evaluation suite và training candidate không được join vào active knowledge.

## Done when

- Source Register entry pin exact revision/checksum, provenance, classification,
  rights, ACL, retention, deletion method và approval evidence.
- Candidate materialization pin release/source/embedding/retriever revisions và
  vượt malware/PII/secret/license/quality gates.
- Independent evaluation đạt citation/refusal/ACL/security rubric; human
  maker-checker approve và Release Owner activate.
- Atomic pointer activation, cache invalidation, critical barrier, rollback,
  tombstone, kill switch và DSAR lineage được rehearsal.
- Production-like retrieval smoke chứng minh đúng source revision/citation và
  không đọc candidate, stale hoặc unauthorized chunk.

## Checkpoint

- Exact next action: chờ Data Owner cung cấp một source package được phê duyệt;
  khi chưa có, chuyển `blocked` với blocker rõ thay vì yêu cầu cloud credential.

## Evidence

- [ ] `npm run verify:ai` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
