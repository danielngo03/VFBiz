---
id: VFBIZ-0123
title: Release-pinned conversation budget policy
status: proposed
mode: controlled
priority: P0
owner_team: customer-engagement
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/engagement/application
  - backend/api/src/modules/engagement/domain
  - backend/api/src/modules/engagement/infrastructure
  - backend/api/src/platform/config
  - backend/api/test
depends_on:
  - VFBIZ-0115
controlled_signals:
  - customer-conversation
  - ai-finops
  - ai-release
exclusive_resources:
  - ai-budget-policy
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 1
review_date: "2026-08-26"
---

# Outcome

Mọi conversation/session/turn budget được resolve từ một immutable policy pin
theo assistant profile, market, tenant và AI release; reservation, provider
usage, fallback attempt và reconciliation tạo audit evidence giải thích được
chi phí thay vì dùng số hard-code trong controller/service.

## Constraints

- NestJS sở hữu business quota và admission; Model Mesh chỉ thực thi budget đã
  được signed envelope cấp và trả normalized usage.
- Policy có effective window, version, price-book revision, currency và
  optimistic concurrency; environment chỉ chọn bootstrap fallback fail-closed.
- Budget áp dụng theo request, turn, session, subject và tenant. Không log raw
  prompt, PII hoặc provider secret trong cost ledger.
- Reservation phải giữ worst-case cost trước network call; mọi attempt kể cả
  timeout/fallback đều reconcile hoặc để trạng thái pending có outbox retry.
- Không tự nâng budget vì customer tier, lỗi provider hoặc retry nếu thiếu
  policy đã duyệt.

## Done when

- `BudgetPolicyResolver` thay toàn bộ token/micro-cost magic numbers trong
  conversation creation/controller/dispatcher.
- Signed API→AI request pin policy revision, price-book revision và remaining
  budget; FastAPI không được tự mở rộng giới hạn.
- PostgreSQL lưu reservation, incurred usage, reconciliation state và immutable
  attribution theo release/request/session/subject/tenant.
- Concurrent turns, duplicate response, cancellation, late usage, fallback và
  provider reconciliation không double-charge hoặc mất chi phí.
- Redis/database/provider outage có typed fail-closed/degraded behavior; cost
  telemetry không làm chết final response commit.
- Unit/integration tests bao phủ policy expiry, stale revision, over-budget,
  concurrency, idempotency và outbox retry.

## Checkpoint

- Exact next action: bắt đầu sau VFBIZ-0115 để dùng cùng resolved release
  snapshot và normalized provider attempt ledger.

## Evidence

- [ ] `npm run verify:api` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
