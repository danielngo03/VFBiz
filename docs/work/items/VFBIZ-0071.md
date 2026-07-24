---
id: VFBIZ-0071
title: Customer Garage journey
status: active
mode: controlled
priority: P0
owner_team: customer-web-experience
accountable_role: product-owner
primary_workspace: customer-portal
affected_workspaces:
  - customer-portal
allowed_paths:
  - apps/customer-portal/src/app/(account)/account/garage
  - apps/customer-portal/src/features/garage
  - apps/customer-portal/src/features/vehicle-catalog
  - apps/customer-portal/src/lib
  - apps/customer-portal/tests
  - docs/work/items/VFBIZ-0071.md
  - WORK.md
depends_on:
  - VFBIZ-0069
controlled_signals:
  - customer-data
  - vehicle-data
exclusive_resources: []
required_checks:
  - npm run verify:apps
  - npm run verify:apps:e2e
revision: 3
review_date: "2026-08-24"
updated_at: "2026-07-24T08:35:17.901Z"
---

# Outcome

Khách hàng quản lý Garage từ approved catalog mà không thể tự xác minh xe hoặc
đưa raw VIN vào flow.

## Constraints

- Không nhận, log hoặc lưu raw VIN trong journey này.
- Customer không được tự chuyển trạng thái vehicle association sang verified.
- Chỉ dùng model/variant từ approved public catalog; không mở scope commerce.

## Done when

- List/add/rename/primary/remove và mọi trạng thái xác minh được thể hiện đúng.
- Invalid variant, stale data, conflict và provider outage có failure state.
- Browser và accessibility evidence đầy đủ.

## Checkpoint

- Waiting for VFBIZ-0069.
- Exact next action: transition to ready after dependency is done.

## Evidence

- [ ] Browser acceptance.
