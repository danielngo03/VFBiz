---
id: VFBIZ-0025
title: Active retriever foundation
status: done
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/modules/knowledge
  - backend/ai/migrations/versions
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
  - database-migration
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 7
review_date: "2026-08-23"
updated_at: "2026-07-25T09:45:55.103Z"
---

# Outcome

Retriever chỉ đọc một active Knowledge Release đúng profile/domain/locale/ACL,
trả typed evidence/updating/unavailable/no-evidence outcome và được kiểm chứng
bằng synthetic release fixture; activation business source thật thuộc
VFBIZ-0100 để không giả mạo human Data/Legal/Privacy/Release approval.

## Constraints

- Ingestion worker không review hoặc activate candidate của chính mình.
- Không dùng public source candidate đang `legal-hold`/`rejected`.
- Chỉ dùng synthetic fixture để test code; synthetic fixture không được trình
  bày như business fact hoặc production-ready Knowledge Release.
- Evaluation/red-team/training split không được join vào active knowledge.

## Done when

- Hybrid lexical/vector retriever và reranker pin active pointer, ACL, source
  revision, freshness và citation.
- Một query chỉ đọc revision-coherent snapshot; ACL lọc trước retrieval và được
  kiểm lại trước response.
- Candidate/active isolation, critical revision barrier, rollback và tombstone
  được chứng minh bằng integration test.
- Typed updating/blocked/missing/unavailable outcome được Assistant layer có thể
  map thành refusal/handoff mà không dùng stale fact.
- Synthetic integration fixture chứng minh active/candidate isolation và
  cross-ACL denial; code không tự approval.
- Materialization contract ghi đủ release ID, source revision, ACL, embedding
  revision và credential-free citation attributes.

## Checkpoint

- Retrieval/materialization code foundation đã hoàn tất và được independent
  review không còn P0/P1.
- Business Knowledge Release vẫn thuộc VFBIZ-0100 và chỉ được mở khi Data Owner
  cung cấp approved source cùng rights evidence.

## Evidence

- [x] `npm run verify:ai` — Ruff, Pyright, Alembic và 177 tests đạt.
- [x] `npm run governance:check` — 100 work items và 61 routing scenarios đạt.
- [x] PostgreSQL 17 + pgvector — migration head `20260725_0008`,
  downgrade/upgrade roundtrip và 4/4 DB integration tests đạt.
- [x] Independent risk review — không còn P0/P1; checksum tamper giữ nguyên row
  count bị activation/retrieval chặn fail-closed.
