---
id: VFBIZ-0022
title: Knowledge Release control plane
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
revision: 1
review_date: "2026-08-23"
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
- Critical-domain `RAG_SYNCING` barrier ngăn đọc revision nửa cũ nửa mới.
- Migration/repository/domain/security tests và release manifest validation đạt.

## Checkpoint

- Exact next action: materialize release aggregate bằng synthetic fixture sau
  VFBIZ-0021; chưa download/crawl/embed business content.

## Evidence

- [ ] `npm run verify:ai` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
