---
id: VFBIZ-0084
title: Đăng ký read-only plan_ev_trip tool
status: proposed
mode: controlled
priority: P1
owner_team: mobility-platform
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
  - ai
  - root
allowed_paths:
  - backend/api/src/modules/engagement
  - backend/api/src/modules/mobility
  - backend/ai/app/modules/assistant
  - backend/ai/app/modules/tooling
  - backend/ai/tests/contract/assistant
  - contracts/ai
  - contracts/openapi
  - docs/work/items/VFBIZ-0084.md
  - docs/work/plans/VFBIZ-0077.md
depends_on:
  - VFBIZ-0024
  - VFBIZ-0038
  - VFBIZ-0082
controlled_signals:
  - ai-tool
  - authorization
  - ev-trip-planner
  - public-contract
  - trip-correctness
exclusive_resources:
  - public-contract
required_checks:
  - npm run contracts:lint
  - npm run verify:api
  - npm run verify:ai
plan: docs/work/plans/VFBIZ-0077.md
revision: 1
review_date: "2026-08-24"
---

# Outcome

Customer AI Assistant có thể đề xuất `plan_ev_trip` theo schema; NestJS kiểm
subject, vehicle scope, quota và thực thi planner read-only trước khi trả result.

## Constraints

- FastAPI không gọi provider/business database trực tiếp và không tự mutation.
- Tool schema, timeout, quota, authorization và audit được pin theo revision.
- Tool result qua freshness/anomaly gate; missing evidence dẫn tới refusal hoặc
  handoff recommendation, không phỏng đoán.
- Handoff không được đăng ký như AI tool.

## Done when

- Invalid schema/scope/vehicle ownership và stale fencing bị từ chối.
- Tool call duplicate được idempotent; cancellation truyền xuống planner job.
- AI chỉ diễn giải typed TripPlan và giữ citations/source revision.
- Contract parity và cross-workspace integration tests đạt.

## Decisions and assumptions

- Tool baseline chỉ pre-trip planning; không side effect hoặc live reroute.

## Checkpoint

- Exact next action: Integration Owner cấp contract lease sau dependencies.

## Evidence

- [ ] `npm run contracts:lint` — add observed evidence
- [ ] `npm run verify:api` — add observed evidence
- [ ] `npm run verify:ai` — add observed evidence
