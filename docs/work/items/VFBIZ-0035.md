---
id: VFBIZ-0035
title: Quarantine legacy ownership schema
status: done
mode: controlled
priority: P1
owner_team: customer-product
accountable_role: data-owner
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/prisma/models/ownership.prisma
  - backend/api/src/modules/ownership
  - backend/api/test/architecture
depends_on:
  - VFBIZ-0016
controlled_signals:
  - vehicle-ownership
  - pii
exclusive_resources: []
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 5
review_date: "2026-08-23"
updated_at: "2026-07-23T08:28:10.609Z"
---

# Outcome

Legacy ownership model không thể bị Customer Chatbot, Vision hoặc Operations
vô tình sử dụng như bằng chứng khách hàng sở hữu xe.

## Constraints

- Không materialize Vehicle Asset mới khi chưa có DMS/CRM contract.
- Không coi Garage self-reported là verified ownership.
- Nếu schema chưa thể xóa, composition root và architecture test phải chặn use.
- Không migrate raw VIN vào model mới bằng giả định.

## Done when

- Legacy module không còn runtime entrypoint/consumer.
- Architecture test chặn import/use ngoài migration/history boundary.
- Docs và capability map ghi prerequisite verified association cho Vision.
- Không có public/admin contract dựa vào `externalVehicleRef` tự do.

## Checkpoint

- Exact next action: trace consumer của ownership schema; xóa/quarantine theo
  evidence và không tạo replacement giả.

## Evidence

- [x] `npm run verify:api` — 24 unit suites/110 tests, 7 E2E
  suites/36 tests, lint, typecheck, Prisma validation và build đạt ngày
  2026-07-23.
- [x] `npm run governance:check` — 55 provider-neutral context scenarios và
  toàn bộ governance gate đạt ngày 2026-07-23.

### ready — 2026-07-23T08:14:29.699Z

Ownership schema is unused by composition root but unsafe as a future authority; quarantine boundary can be enforced without inventing a replacement.

### active — 2026-07-23T08:14:29.996Z

Trace and quarantine legacy ownership records; add architecture enforcement and preserve migrations/history.

### checkpoint — 2026-07-23

Architecture guard dùng TypeScript AST để chặn runtime import, Prisma
delegate/property, raw SQL tới legacy table và `externalVehicleRef` có thể suy
ra tĩnh. Bộ negative fixtures đạt 9/9. Guard này không thay thế database
permission, migration review hoặc privacy test cho raw VIN.

### review — 2026-07-23T08:28:10.262Z

Independent risk review completed; one bounded fix cycle closed AST, bypass-fixture and portability findings.

### done — 2026-07-23T08:28:10.609Z

Legacy ownership runtime use is quarantined; physical schema removal remains a separate controlled migration after DMS/CRM evidence.
