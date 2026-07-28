---
id: VFBIZ-0134
title: Dataset Registry intake foundation
status: done
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai/app/modules/datasets
  - backend/ai/tests/unit/datasets
  - backend/ai/tests/integration/datasets
  - backend/ai/docs/dataset-engineering.md
  - docs/work/items/VFBIZ-0134.md
  - WORK.md
depends_on:
  - VFBIZ-0133
  - VFBIZ-0140
  - VFBIZ-0141
controlled_signals:
  - dataset-source
  - dataset-release
  - migration
exclusive_resources:
  - ai-dataset-registry
  - database-migration
required_checks:
  - npm run verify:ai
  - npm run contracts:lint
  - npm run governance:check
revision: 6
review_date: "2026-08-28"
updated_at: "2026-07-28T04:22:06.641Z"
---

# Outcome

AI PostgreSQL và object storage cung cấp nền tảng Source Register,
fetch/quarantine và content-addressed artifact theo immutable digest. Migration
đã dự phòng schema cho lineage, quality evidence, release pointer và tombstone;
runtime của các phần đó thuộc các work item Dataset Product/Release tiếp theo.

## Constraints

- Chỉ bắt đầu migration sau khi VFBIZ-0133 được review/done và database-migration lease trống.
- Payload lớn không nằm trong PostgreSQL hoặc Git.

## Done when

- Source/fetch/artifact state machines reject invalid transitions and stale versions.
- Registry persists source, fetch and artifact metadata; duplicate fetch
  delivery is idempotent and conflicting replay is rejected.
- Content-addressed storage enforces trust zones, bounded writes, digest verification and no symlink escape.
- PostgreSQL integration proves source/fetch/artifact replay safety. Lineage,
  quality, maker-checker release and tombstone acceptance remain outside this
  foundation.

## Checkpoint

- Exact next action: VFBIZ-0148 consumes the schema to implement Dataset
  Product/Recipe lineage; VFBIZ-0152 owns release and tombstone runtime.

## Evidence

- [x] `npm run verify:ai` — 393 tests passed; 79 external-integration skips remain explicit
- [x] `npm run contracts:lint` — canonical dataset vectors and public contracts passed
- [x] `npm run governance:check` — passed with Dataset Platform ownership and instruction budgets

### ready — 2026-07-28T04:03:07.760Z

Canonical contracts, ownership and migration 0016 are complete.

### active — 2026-07-28T04:03:08.106Z

Implementing Dataset Registry domain, application and infrastructure layers.

### review — 2026-07-28T04:22:06.297Z

Source/fetch/artifact runtime, local content-addressed adapter and real
PostgreSQL integration passed review. Broader Dataset Product/Release runtime
is not claimed by this item.

### done — 2026-07-28T04:22:06.641Z

Dataset Registry intake foundation completed with migration 0016, explicit
idempotent fetch replay and architecture inventory.
