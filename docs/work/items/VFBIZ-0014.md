---
id: VFBIZ-0014
title: Customer Profile, Consent và DSAR foundation
status: done
mode: controlled
priority: P0
owner_team: customer-product
accountable_role: privacy-owner
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/customer
  - backend/api/prisma/models/customer.prisma
  - backend/api/prisma/migrations
  - backend/api/test
  - contracts/openapi
  - packages/api-client
  - backend/api/docs
  - docs/work
  - WORK.md
depends_on:
  - VFBIZ-0013
controlled_signals:
  - customer-profile
  - consent
  - customer-data
  - pii
  - schema
  - migration
  - public-contract
exclusive_resources:
  - database-migration
  - public-contract
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 5
review_date: "2026-08-23"
updated_at: "2026-07-23T05:57:38.343Z"
---

# Outcome

Khách hàng đã xác thực đọc/cập nhật hồ sơ của chính mình, quản lý consent và tạo
yêu cầu DSAR theo contract có concurrency, idempotency và audit rõ ràng.

## Constraints

- API chỉ lưu opaque `(issuer, subject)`; Keycloak/CIAM sở hữu credential, MFA,
  email verification và password recovery.
- Profile không nhận field identity hoặc role từ request body.
- Consent là append-only event; không update lịch sử.
- DSAR chỉ tạo workflow request, không tuyên bố đã xóa hoặc export khi worker
  downstream chưa hoàn tất.
- Retention matrix và production delete authority vẫn cần Privacy Owner duyệt.

## Done when

- `GET/PATCH /api/v1/me` enforce customer principal và optimistic concurrency.
- Preferences có schema typed; không dùng JSON `{}` không kiểm soát.
- Consent event pin purpose, policy version, state, source, timestamp và
  correlation ID; replay không tạo sự kiện trùng.
- Export/delete request dùng `Idempotency-Key`, có lifecycle hợp lệ và không
  trả artifact private qua public URL.
- Customer A không đọc/sửa profile, consent hoặc DSAR của Customer B.
- OpenAPI, generated SDK, migration và tests quan sát đúng runtime.

## Checkpoint

- Profile, Consent và DSAR request vertical slices đã được tích hợp vào
  `CustomerModule`; exact next action là đóng work item và tiếp tục Vehicle
  Catalog VFBIZ-0015.

## Evidence

- [x] `npm run verify:api` — lint/typecheck, 45 unit/architecture tests,
  16 E2E tests, Prisma validation và Nest build đạt ngày 2026-07-23.
- [x] `npm run governance:check` — 49 durable docs, 13 work item,
  37 routing scenario và instruction budget đạt ngày 2026-07-23.

Evidence bổ sung:

- `npm run test:migrations --workspace=@vfbiz/api` — clean replay, zero drift
  và legacy fixture backfill đạt với 3 migration.
- `npm run contracts:lint` và API client typecheck đạt; SDK đã regenerate.

Residual scope: DSAR worker fan-out/hard-delete, BFF callback/session revoke và
retention approval production là work item riêng; API không tuyên bố request
`requested` đã hoàn tất.
