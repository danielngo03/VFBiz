---
id: VFBIZ-0136
title: First-party VinFast knowledge source release
status: proposed
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai
  - contracts/ai
  - docs/work/items/VFBIZ-0136.md
  - WORK.md
depends_on:
  - VFBIZ-0133
controlled_signals:
  - dataset-source
  - knowledge-ingestion
  - dataset-release
exclusive_resources:
  - ai-source-registry
  - ai-knowledge-release-registry
required_checks:
  - npm run verify:ai
  - npm run contracts:lint
  - npm run governance:check
revision: 1
review_date: "2026-08-28"
---

# Outcome

Một nguồn VinFast first-party thật đi qua provenance, quarantine, scan,
maker-checker và atomic Knowledge Release.

## Constraints

- Content, Legal và Data Owner phải cung cấp source revision cùng approval thật.
- Không crawl hoặc tạo VinFast fact thay cho authority.

## Done when

- Released source có immutable hashes, approval evidence, rollback và tombstone test.

## Checkpoint

- Human-blocked: cần Content/Legal/Data Owner chọn và phê duyệt exact source.

## Evidence

- [ ] `npm run verify:ai` — add evidence reference
- [ ] `npm run contracts:lint` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
