---
id: VFBIZ-0141
title: Provision Dataset Registry persistence
status: done
mode: controlled
priority: P0
owner_team: ai-platform-foundation
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/migrations
  - docs/work/items/VFBIZ-0141.md
  - WORK.md
depends_on:
  - VFBIZ-0133
  - VFBIZ-0140
controlled_signals:
  - dataset-release
  - migration
exclusive_resources:
  - database-migration
  - ai-dataset-registry
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 5
review_date: "2026-08-28"
updated_at: "2026-07-28T04:02:44.215Z"
---

# Outcome

Provision the durable PostgreSQL schema required by the Dataset Registry while
keeping large payloads in content-addressed object storage.

## Constraints

- Production operation is forward-only and extends the existing dataset
  release table. Development downgrade is permitted only while the new
  governed tables and columns contain no data.
- PostgreSQL stores metadata, state, evidence and immutable pointers, not large
  dataset payloads.
- State, digest, lineage and separation-of-duties invariants are enforced in
  database constraints where practical.

## Done when

- Alembic upgrades from the current head. An isolated empty database may
  downgrade; downgrade fails closed once governed data exists.
- Source, fetch, artifact, lineage, quality, release pointer and tombstone records have explicit integrity constraints.
- Existing Assistant Release tables remain compatible.

## Checkpoint

- Exact next action: lease the AI migration head and add one isolated revision.

## Evidence

- [x] `npm run verify:ai` — 388 tests passed; static Alembic chain reached 0016
- [x] `npm run governance:check` — passed before migration checkpoint

### ready — 2026-07-28T03:58:07.803Z

Dataset Platform ownership and canonical contracts are complete.

### active — 2026-07-28T03:58:08.119Z

Provisioning an isolated Dataset Registry migration.

### review — 2026-07-28T04:02:43.924Z

Migration upgraded, safely downgraded while empty and upgraded again on local
PostgreSQL. A destructive-downgrade test proves governed data blocks rollback.

### done — 2026-07-28T04:02:44.215Z

Dataset Registry schema provisioned with guarded development downgrade and
destructive-rollback protection. Production rollback remains forward-fix.
