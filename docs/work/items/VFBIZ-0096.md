---
id: VFBIZ-0096
title: Customer Portal chat experience
status: proposed
mode: controlled
priority: P0
owner_team: customer-web-experience
accountable_role: engineering-lead
primary_workspace: customer-portal
affected_workspaces:
  - customer-portal
allowed_paths:
  - apps/customer-portal/src/app
  - apps/customer-portal/src/features
  - apps/customer-portal/src/components
  - apps/customer-portal/tests
  - apps/customer-portal/docs
depends_on:
  - VFBIZ-0095
  - VFBIZ-0098
controlled_signals:
  - customer-journey
  - customer-conversation
  - accessibility
  - customer-privacy
exclusive_resources: []
required_checks:
  - npm run governance:check
  - npm run verify:apps
revision: 1
review_date: "2026-07-25"
---

# Outcome

Customer Portal cung cấp chat experience accessible cho public và authenticated
customer, reconnect được session/stream và hiển thị citation, refusal, lỗi cùng
handoff mà không mang bearer token xuống browser.

## Constraints

- Next.js BFF/DAL giữ token server-side; browser chỉ dùng opaque session/capability.
- Không hiển thị chain-of-thought hoặc trạng thái giả như “đã kết nối nhân viên”.
- Không thêm client state library khi chưa có consumer cần thiết.
- UI phải dùng design tokens/component convention hiện có và WCAG AA.

## Done when

- Session start, message composer, transcript, progress, citation drawer,
  cancel/retry-safe behavior và reconnect từ durable cursor hoạt động.
- Public capability và authenticated session không bị trộn khi login/logout.
- Offline/provider unavailable, resync required, refusal và handoff pending/
  connected/expired có customer-safe state.
- Keyboard, focus, screen reader, reduced motion, mobile layout và axe đạt.
- Playwright chứng minh refresh/tab close/network interruption không mất final
  answer hoặc handoff state.

## Checkpoint

- Exact next action: start sau VFBIZ-0095 và generated customer API/BFF contract
  được regenerate; không dựng UI trên candidate endpoint.

## Evidence

- [ ] `npm run governance:check` — add evidence reference
- [ ] `npm run verify:apps` — add evidence reference
