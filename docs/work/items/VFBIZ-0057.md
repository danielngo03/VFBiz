---
id: VFBIZ-0057
title: Rename and scaffold Next.js Workforce Portal
status: done
mode: controlled
priority: P0
owner_team: workforce-experience
accountable_role: engineering-lead
primary_workspace: workforce-portal
affected_workspaces:
  - workforce-portal
allowed_paths:
  - apps/workforce-portal
  - docs/work/items/VFBIZ-0057.md
  - docs/work/plans/VFBIZ-0055.md
depends_on:
  - VFBIZ-0055
controlled_signals:
  - authentication
  - authorization
  - workforce-admin
exclusive_resources: []
required_checks:
  - npm run verify:apps
revision: 3
review_date: "2026-08-24"
updated_at: "2026-07-24T22:15:00.000+07:00"
---

# Outcome

Workspace được đổi thành `apps/workforce-portal` và có Next.js App Router
foundation, server-only BFF boundary, design tokens cùng authorization UX shell.

## Constraints

- Không lưu token/capability trong browser storage.
- Portal không quyết định quyền thay NestJS.
- Server Components mặc định; Client Components chỉ cho interaction.
- Không sửa root lockfile trong delegated lane.

## Done when

- Package/workspace source đổi tên nhất quán.
- Next.js route/layout, DAL/session contract và role/assignment/approval shell
  typecheck/test đạt.
- README, local architecture, UX và design docs phản ánh runtime thật.

## Checkpoint

- Workspace đã đổi thành `apps/workforce-portal`.
- Next.js App Router, OIDC Authorization Code + PKCE, encrypted Redis token
  vault, opaque browser session, generated workforce SDK, local design tokens
  và UX/docs foundation đã được tạo.
- Sign-in/callback/logout chạy server-side; ID token được xác minh signature,
  issuer, audience, nonce và session cookie không chứa token.
- Exact next action: VFBIZ-0058 nối role/assignment/approval views vào API thật.

## Evidence

- [x] Static source inspection: không dùng `localStorage`/`sessionStorage`, token
  interfaces chỉ nằm dưới `src/lib/server`.
- [x] Dependency lockfile được cập nhật và generated workforce SDK typecheck đạt.
- [x] Portal lint, typecheck, 5 unit tests và production build đạt.
- [x] Playwright Chromium smoke: 2/2 scenario đạt.
