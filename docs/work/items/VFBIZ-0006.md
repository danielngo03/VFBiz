---
id: VFBIZ-0006
title: Chuẩn hóa docs và skill API Foundation
status: done
mode: bounded
priority: P1
owner_team: api-foundation
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/AGENTS.md
  - backend/api/README.md
  - backend/api/docs
  - backend/api/.agents/skills/evolve-backend-capability
depends_on: []
controlled_signals: []
exclusive_resources: []
required_checks:
  - governance
  - skill-validation
  - context-routing
revision: 5
review_date: "2026-08-23"
updated_at: "2026-07-22T18:25:41.927Z"
---

# Outcome

Agent làm việc trong `backend/api` tìm đúng boundary, integration policy, data
ownership và workflow capability mà không đọc root implementation detail.

## Constraints

- Chỉ sửa instruction, docs và skill; không refactor runtime NestJS.
- Một canonical layout nằm trong capability reference; architecture chỉ giữ
  dependency/boundary bền vững.

## Done when

- API docs không chứa current work state, class name hoặc migration ID dễ stale.
- Có policy integration adapter đủ timeout/retry/webhook/idempotency/freshness.
- `evolve-backend-capability` là workflow ngắn và trỏ đúng reference/docs.
- API docs/skill route về `api-foundation` và governance checks đạt.

## Checkpoint

- Exact next action: cập nhật API instructions/docs/skill theo audit read-only.

## Evidence

- [x] `governance` — `npm run governance:check` đạt với 25 scenarios.
- [x] `skill-validation` — `quick_validate.py backend/api/.agents/skills/evolve-backend-capability` trả `Skill is valid!`.
- [x] `context-routing` — API composition root được route tới `api-foundation`, 0 extra docs; commit `6b991ad`.
