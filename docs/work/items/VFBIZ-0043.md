---
id: VFBIZ-0043
title: Native PostgreSQL và PostGIS local readiness
status: review
mode: controlled
priority: P0
owner_team: reliability-engineering
accountable_role: engineering-lead
primary_workspace: infra
affected_workspaces:
  - infra
  - api
allowed_paths:
  - infra/local
  - backend/api/.env.example
  - backend/api/README.md
  - backend/api/package.json
  - backend/api/scripts
  - docs/work/items
depends_on: []
controlled_signals:
  - migration
exclusive_resources:
  - database-migration
required_checks:
  - npm run test:migrations --workspace @vfbiz/api
  - npm run governance:check
revision: 4
review_date: "2026-07-23"
updated_at: "2026-07-23T15:20:45.203Z"
---

# Outcome

Developer dùng PostgreSQL/PostGIS native trên localhost có thể bootstrap role,
database và extension idempotently, chạy toàn bộ migration và readiness check
mà không cần Docker.

## Constraints

- Không tự cài Homebrew/system package từ agent script.
- Script không drop database hoặc thay password nếu thiếu explicit flag.
- PostgreSQL/PostGIS version phải nằm trong compatibility matrix được kiểm thử.

## Done when

- Preflight báo rõ PostgreSQL version, PostGIS availability và quyền còn thiếu.
- Bootstrap tạo role/database/extension idempotently bằng local admin.
- Migration deploy và clean/legacy replay đạt.
- README có recovery cho failed migration trên database local rỗng.

## Checkpoint

- PostgreSQL `17.10` và PostGIS `3.6.4` chạy native trên
  `127.0.0.1:5434`; PostgreSQL 14 trên cổng `5432` không bị thay đổi.
- Database `vfbiz`, role local và PostGIS extension đã được bootstrap
  idempotently; cả tám migration hiện tại đã được deploy.
- Migration verifier đã chuyển khỏi Docker sang hai database native tạm thời,
  tự cleanup sau clean replay và legacy replay.
- Exact next action: focused review scripts và tài liệu recovery, sau đó
  acceptance bởi Engineering Lead.

## Evidence

- [x] `npm run db:local:bootstrap --workspace @vfbiz/api` — PostgreSQL 17,
  PostGIS 3.6.4 và database local ready.
- [x] `npm run db:local:check --workspace @vfbiz/api` — readiness đạt.
- [x] `npm run test:migrations --workspace @vfbiz/api` — clean replay, schema
  drift, 7 PostgreSQL integration tests và legacy backfill đạt.
- [x] `npm run governance:check` — 41 work item và 55 provider-neutral
  scenarios đạt.
- [x] `npm run verify:api` — lint, typecheck, 135 unit/integration tests,
  47 E2E tests, Prisma validation và build đạt.
