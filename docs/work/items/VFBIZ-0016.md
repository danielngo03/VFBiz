---
id: VFBIZ-0016
title: Customer Garage self-reported foundation
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
  - VFBIZ-0014
  - VFBIZ-0015
controlled_signals:
  - customer-garage
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
updated_at: "2026-07-23T06:23:14.595Z"
---

# Outcome

Khách hàng quản lý Garage tự khai báo của chính mình bằng model/variant đã phát
hành mà không bị trình bày nhầm là xe đã xác minh quyền sở hữu.

## Constraints

- Garage entry, physical vehicle và verified ownership là ba khái niệm khác
  nhau; không gộp bằng một `verificationState` mơ hồ.
- Baseline không nhận raw VIN. VIN/tokenization chỉ mở bằng work item ownership
  riêng khi DMS adapter và Privacy/Security design đã được duyệt.
- Request không được tự đặt `verified`, association ID hoặc source authority.
- Delete Garage entry không xóa Vehicle Catalog hoặc audit evidence.

## Done when

- CRUD `/api/v1/me/vehicles` enforce subject ownership và optimistic concurrency.
- Entry lưu claimed variant, nickname, primary flag, source và version; trạng
  thái ownership là derived/unavailable, không do client ghi.
- Chỉ variant từ approved active Catalog release được chọn.
- Customer A không đọc/sửa/xóa Garage entry của Customer B.
- Duplicate/default-primary rules deterministic; mutation idempotent.
- Contract, SDK, migration và negative authorization tests đạt.

## Checkpoint

- Customer Garage self-reported lifecycle, Product eligibility port,
  subject-scoped API, ETag/OCC, idempotency và additive SDK đã hoàn tất.
- Exact next action: đóng work item sau governance gate rồi mở Conversation
  Runtime bằng work item riêng, không sửa LangGraph trong cùng lane.

## Evidence

- [x] `npm run verify:api` — 52 unit/architecture tests, 23 E2E tests,
  lint/typecheck/Prisma validate/Nest build đạt ngày 2026-07-23.
- [x] `npm run governance:check` — 49 durable docs, 13 work item và 38
  provider-neutral routing scenario đạt ngày 2026-07-23.

Evidence bổ sung:

- Migration replay đạt trên clean database và legacy staging fixture với năm
  migration, zero schema drift; migration fail-closed nếu legacy VIN hoặc
  verification evidence tồn tại.
- `npm run contracts:lint`, generated TypeScript SDK và SDK typecheck đạt.
- Negative E2E từ chối workforce principal, UUID sai, thiếu ETag và client input
  cố gửi VIN/source/verified ownership.
- Review finding fingerprint được xử lý một vòng: contract/runtime drift,
  freshness/market, replay ordering, primary version, transaction retry,
  source mapping và route UUID.

Residual scope: cross-database DMS/VIN ownership verification không thuộc
Garage foundation và chỉ mở khi có provider, Privacy/Security design cùng
ownership work item riêng.
