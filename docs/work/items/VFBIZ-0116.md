---
id: VFBIZ-0116
title: Persist Assistant Release activation history
status: done
mode: controlled
priority: P0
owner_team: ai-platform-foundation
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/platform/database
  - backend/ai/app/bootstrap
  - backend/ai/migrations
  - backend/ai/tests/architecture
  - backend/ai/tests/contract
  - backend/ai/tests/integration/platform
  - backend/ai/tests/unit/bootstrap
depends_on:
  - VFBIZ-0104
  - VFBIZ-0118
  - VFBIZ-0119
controlled_signals:
  - ai-release
  - ai-safety
  - migration
exclusive_resources:
  - database-migration
  - ai-assistant-release-manifest
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 10
review_date: "2026-07-26"
updated_at: "2026-07-26T10:29:26.150Z"
---

# Outcome

PostgreSQL lưu immutable release candidate, activation envelope, approval/gate
evidence, append-only activation history và active pointer bằng migration có
OCC/rollback/restart recovery, sẵn sàng cho repository của AI Assurance.

## Constraints

- Chỉ sở hữu database/bootstrap primitives; không triển khai resolver business
  rules hoặc Model Mesh.
- Candidate immutable; activation promotion/revoke/rollback tạo history event,
  không rewrite bằng update tùy ý.
- Active pointer thay đổi bằng expected revision và transaction.
- Promotion envelope pin candidate digest, effective window, rollback target,
  live controls và promotion evidence digest.
- Không seed production approval giả hoặc secret.

## Done when

- Migration tạo tables, constraints, indexes và immutable/history triggers.
- Schema hỗ trợ repository thực hiện active-pointer OCC bằng conditional write;
  repository semantics thuộc VFBIZ-0114.
- Rollback target FK/history chứng minh target từng active hoặc superseded.
- Bootstrap compose/close database components mà không bật provider runtime.
- Architecture/contract tests kiểm dependency direction và schema constraints.
- Alembic upgrade/downgrade dry-run cùng PostgreSQL integration đạt, không skip.

## Checkpoint

- PostgreSQL 17.10/pgvector 0.8.5 lưu candidate, activation, append-only
  history, active pointer và outbox trong cùng authority boundary.
- Database bind candidate digest, canonical history hash, pinned
  rollback/revoke target và deferred history/pointer/outbox atomicity.
- Hai vòng review đã đóng toàn bộ finding bằng evidence mới; không mở vòng ba.
- Exact next action: VFBIZ-0114 triển khai repository/resolver trên persistence
  contract này, không compose Model Mesh trong lane persistence.

## Evidence

- [x] `npm run verify:ai` — Ruff/Pyright/Alembic đạt; 270 tests passed.
- [x] `npm run governance:check` — 71 provider-neutral scenarios và generated
  checks đạt trên integrated main.
- [x] `npm run verify:ai:integration` — 59 PostgreSQL 17.10/pgvector 0.8.5
  tests passed, zero skipped; image digest evidence recorded in review ledger.
- [x] Independent verifier và risk reviewer — approved HEAD `eb3b4ad`; four
  High findings closed at cycle 2.

### review — 2026-07-26T10:29:25.680Z

Implementation complete; verifier and risk review evidence attached

### done — 2026-07-26T10:29:26.150Z

Accepted at eb3b4ad after cycle-2 risk sign-off
