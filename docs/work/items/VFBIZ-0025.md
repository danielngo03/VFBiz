---
id: VFBIZ-0025
title: Active retriever và Knowledge Release đầu tiên
status: proposed
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/modules/knowledge
  - backend/ai/docs/knowledge-release.md
  - backend/ai/docs/evaluation-and-release.md
  - backend/ai/tests/unit/knowledge
  - backend/ai/tests/integration/knowledge
  - backend/ai/tests/evaluation
depends_on:
  - VFBIZ-0022
  - VFBIZ-0023
controlled_signals:
  - ai-retrieval
  - ai-release
  - knowledge-revision
  - data-governance
  - license
  - pii
exclusive_resources:
  - ai-knowledge-release-registry
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 1
review_date: "2026-08-23"
---

# Outcome

Retriever chỉ đọc một active Knowledge Release đúng profile/domain/locale/ACL,
và release đầu tiên chỉ được activate sau independent evaluation cùng human
Data/Legal/Privacy/Release approval.

## Constraints

- Ingestion worker không review hoặc activate candidate của chính mình.
- Không dùng public source candidate đang `legal-hold`/`rejected`.
- Thiếu approved VinFast source thì work item giữ `blocked` hoặc dùng synthetic
  fixture để test code; synthetic fixture không được trình bày như business fact.
- Evaluation/red-team/training split không được join vào active knowledge.

## Done when

- Retriever pin active pointer, ACL, source revision, freshness và citation.
- Candidate/active isolation, critical revision barrier, rollback và tombstone
  được chứng minh bằng integration test.
- Independent evaluation đạt citation/refusal/ACL/security gate đã pin.
- Release evidence ghi human authority references; code không tự approval.
- Kill switch/invalidate cache và rollback rehearsal đạt.

## Checkpoint

- Exact next action: chỉ start sau VFBIZ-0022/0023 và khi Source Register có
  một knowledge source được phê duyệt thật; nếu chưa có thì failed-safely.

## Evidence

- [ ] `npm run verify:ai` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
