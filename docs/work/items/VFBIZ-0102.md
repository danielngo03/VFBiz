---
id: VFBIZ-0102
title: Workforce Support Console experience
status: proposed
mode: controlled
priority: P0
owner_team: workforce-experience
accountable_role: engineering-lead
primary_workspace: workforce-portal
affected_workspaces:
  - workforce-portal
allowed_paths:
  - apps/workforce-portal/src/app
  - apps/workforce-portal/src/features/customer-support
  - apps/workforce-portal/src/platform/api
  - apps/workforce-portal/tests
  - apps/workforce-portal/docs
depends_on:
  - VFBIZ-0098
controlled_signals:
  - support-handoff
  - authorization
  - pii
  - workforce-portal
  - accessibility
exclusive_resources: []
required_checks:
  - npm run verify:apps
  - npm run governance:check
revision: 1
review_date: "2026-07-25"
---

# Outcome

Nhân viên CSKH có capability/scope phù hợp nhận, xem và xử lý durable handoff
case trong Workforce Portal; customer response và lifecycle update được ghi qua
NestJS API mà không đưa bearer token hoặc unrestricted PII xuống browser.

## Constraints

- Portal không phải authorization, assignment hoặc contact-center authority.
- Token nằm server-side BFF; sensitive response `private, no-store`.
- UI không được tuyên bố agent đã connected trước durable API state.
- Không render untrusted customer HTML/Markdown; transcript phải sanitize.

## Done when

- Queue/case detail/transcript/assignment/transfer/resolve view dùng generated
  Workforce client và hiển thị freshness/reconciliation state.
- Capability/scope read-only vs mutation UX rõ; direct API mutation vẫn bị NestJS
  chặn khi UI bị sửa.
- Out-of-order callback, duplicate notification, customer offline, provider
  outage, expired case và consent revoked có typed, accessible state.
- Keyboard/focus/screen-reader/mobile layout và axe/WCAG AA đạt.
- Playwright chứng minh hai workforce subject khác scope không đọc/act chéo case.

## Checkpoint

- Exact next action: start sau VFBIZ-0098 và generated Workforce client được khóa;
  không sửa contract/API trong portal lane.

## Evidence

- [ ] `npm run verify:apps` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
