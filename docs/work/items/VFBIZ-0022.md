---
id: VFBIZ-0022
title: Knowledge Release control plane
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
  - backend/ai/migrations
  - backend/ai/docs/knowledge-release.md
  - backend/ai/tests/unit/knowledge
  - backend/ai/tests/integration/knowledge
depends_on:
  - VFBIZ-0021
controlled_signals:
  - knowledge-revision
  - data-governance
  - license
  - migration
  - schema
  - pii
exclusive_resources:
  - database-migration
  - ai-knowledge-release-registry
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 8
review_date: "2026-08-23"
updated_at: "2026-07-24T21:25:58.865Z"
---

# Outcome

AI Platform quản lý candidate/active Knowledge Release có lineage, ACL,
freshness, atomic activation, rollback/tombstone và critical-domain revision
barrier, nhưng chưa tải hoặc index nguồn thật.

## Constraints

- Knowledge, evaluation, red-team và training purpose không dùng chung release.
- Generator/ingestion worker không tự approve hoặc activate output của mình.
- Source thiếu approved purpose, ACL namespace, rights, checksum hoặc retention
  phải fail closed.
- Registry và migration giữ exclusive lease.

## Done when

- Source Register v2 đã được governance gate xác minh và được dùng read-only;
  lane này không sửa source approval/rights metadata.
- Release pin domain/locale/profile/source/chunking/embedding/policy revision.
- Candidate activation đổi pointer nguyên tử; rollback/tombstone giữ lineage.
- `handoff` là structured graph outcome do API authorize/commit, không phải
  knowledge tool hoặc read-only tool registry entry.
- Critical-domain `RAG_SYNCING` barrier ngăn đọc revision nửa cũ nửa mới.
- Migration/repository/domain/security tests và release manifest validation đạt.

## Checkpoint

- Knowledge Release control plane đã hoàn thành với Source Register v2 snapshot,
  maker-checker, atomic barrier/activation/rollback/tombstone, transactional
  outbox và concurrent idempotency. Chưa download/crawl/embed business content.
- Exact next action: mở VFBIZ-0023 cho ingestion pipeline bằng synthetic source.

## Evidence

- [x] `npm run verify:ai` — 108 passed, 1 skipped; Ruff, Pyright và Alembic SQL đạt tại `01a8a60`
- [x] `npm run governance:check` — đạt sau khi regenerate deterministic indexes/reports
- [x] PostgreSQL 17 integration — concurrent create/barrier/activation, rollback fencing và candidate/active tombstone đạt
- [x] Independent architecture/risk review — hai vòng; không còn P0, các finding cuối đã được xử lý và xác minh bằng race tests

### blocked — 2026-07-24T19:39:15.019Z

Blocked after independent audit: VFBIZ-0021 requires checkpoint identity binding, single-consume resume, strict serialization, authoritative grounding and clean dependency direction before Knowledge Release can safely build on it.

### active — 2026-07-24T20:40:20.036Z

VFBIZ-0090 and VFBIZ-0091 are done; resume Knowledge Release control-plane implementation with synthetic fixtures only.
