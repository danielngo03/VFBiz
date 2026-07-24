---
id: customer-portal-testing
title: Kiểm thử Customer Portal
status: active
owner_role: engineering-lead
scope: customer-portal
when_to_read:
  - customer-portal-test
  - customer-portal-e2e
context_anchors:
  customer-portal-test: "## Taxonomy"
  customer-portal-e2e: "## Gate"
tags:
  - testing
  - nextjs
revision: 1
review_date: 2026-08-24
supersedes: []
---

# Kiểm thử Customer Portal

## Taxonomy

- `tests/unit`: hàm thuần, cấu hình và contract nhỏ.
- `tests/component`: client interaction trong jsdom.
- `tests/integration`: Redis/token-vault và server integration.
- `tests/e2e`: browser journey trên stack local thật.
- `tests/support`: setup và test-only adapter.
- `tests/fixtures`: chỉ tạo khi có fixture được dùng thật.

Report, screenshot, trace, video và coverage không phải test source. Playwright
ghi chúng vào `local-data/test-artifacts/customer-portal`, nằm ngoài workspace
và không được commit.

## Gate

`npm test` chạy unit và component. Thay đổi auth/session cần thêm
`npm run test:integration` và production build. Browser acceptance dùng
`npm run test:e2e:required`; suite bị skip không được tính là evidence.

Skeleton phải giữ bố cục ổn định, không nhận focus và có status dễ hiểu cho
assistive technology. Expected provider failure phải được test như một result
state, không dựa vào `error.tsx`.
