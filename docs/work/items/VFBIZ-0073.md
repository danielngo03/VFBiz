---
id: VFBIZ-0073
title: Next.js portal architecture consolidation
status: active
mode: parallel
priority: P0
owner_team: customer-web-experience
accountable_role: engineering-lead
primary_workspace: customer-portal
affected_workspaces:
  - customer-portal
  - workforce-portal
  - root
allowed_paths:
  - apps/customer-portal
  - apps/workforce-portal
  - packages/portal-session-core
  - package.json
  - package-lock.json
  - tools
  - tests/governance
  - docs/work/items/VFBIZ-0073.md
  - docs/work/plans/VFBIZ-0073.md
  - WORK.md
depends_on:
  - VFBIZ-0069
controlled_signals:
  - authentication
  - customer-data
  - customer-privacy
  - dependency-policy
exclusive_resources:
  - dependency-lockfile
  - public-contract
required_checks:
  - npm run governance:check
  - npm run verify:apps
  - npm run verify:apps:e2e
  - npm run contracts:lint
revision: 5
review_date: "2026-08-24"
updated_at: "2026-07-24T09:19:47.056Z"
---

# Outcome

Customer Portal và Workforce Portal dùng cùng một kiến trúc Next.js
feature-first, có loading/streaming có ý nghĩa, test taxonomy thống nhất và
session platform dùng chung nhưng không làm suy yếu boundary bảo mật.

## Constraints

- Bảo toàn hành vi OIDC, PKCE, token vault, CSRF, logout và authorization hiện có.
- Route layer chỉ composition; business logic nằm trong feature hoặc platform.
- Không thêm capability, API hoặc folder tương lai chưa có consumer.
- Hai writer portal dùng worktree và path riêng; integration owner giữ lockfile,
  shared package, generated client và root scripts.

## Done when

- Không còn loading placeholder lặp; mọi Suspense fallback khớp UI thật.
- Hai portal có cùng dependency rule, test taxonomy và artifact policy.
- Shared session package có contract tests và hai portal giữ policy riêng.
- Không token, secret hoặc trusted capability state xuất hiện trong browser bundle.
- Governance, contracts, portal verification và required browser gates đạt.

## Checkpoint

- Baseline checkpoint: `8f4ba66`; governance/typecheck repair: `b9af612`.
- Customer lane integrated at `6f12220`.
- Workforce lane integrated at `909aa59`.
- Shared session primitives, dependency audit và Workforce logout fence đã
  được tích hợp trên integration branch.
- Customer session platform đã tách OIDC attempt, Redis/encryption runtime và
  refresh/back-channel coordination khỏi session repository.
- Exact next action: chạy authenticated Customer E2E khi có test account rồi
  hoàn tất review/fix dựa trên browser evidence.

## Evidence

- [x] `npm run verify:governance` — đạt, 60 context scenarios.
- [x] `npm run verify:apps` — lint/typecheck/unit/component/integration/build đạt.
- [ ] `npm run verify:apps:e2e` — Workforce 2/2 đạt; Customer fail-closed vì
  thiếu `CUSTOMER_E2E_EMAIL` và `CUSTOMER_E2E_PASSWORD`.
- [x] Customer public browser foundation — 2/2 đạt.
- [x] `npm run contracts:lint` — đạt trong governance gate.
- [x] `npm run verify:portals:dependencies` — không còn unused dependency/file.
