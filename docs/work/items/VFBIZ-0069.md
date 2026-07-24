---
id: VFBIZ-0069
title: Next.js enterprise foundation cho Customer Portal
status: done
mode: controlled
priority: P0
owner_team: customer-web-experience
accountable_role: engineering-lead
primary_workspace: customer-portal
affected_workspaces:
  - customer-portal
allowed_paths:
  - apps/customer-portal
  - docs/work/items/VFBIZ-0069.md
  - WORK.md
depends_on:
  - VFBIZ-0066
  - VFBIZ-0067
controlled_signals:
  - customer-bff
  - design-system
  - accessibility
exclusive_resources:
  - package-lock
required_checks:
  - npm run verify:apps
revision: 5
review_date: "2026-08-24"
updated_at: "2026-07-24T08:34:59.207Z"
---

# Outcome

Customer Portal có App Router structure, secure DAL, design foundation, failure
states và test toolchain đủ để triển khai account journeys an toàn.

## Constraints

- Không triển khai journey Account hoặc Garage trong work item nền tảng.
- Không thêm dependency nếu chưa có consumer trong cùng work item.
- Server Components và server-only DAL là mặc định; không đưa token ra browser.

## Done when

- Route groups, server/client boundaries và security headers được kiểm chứng.
- Design tokens và accessible primitives có consumer thật.
- Lint, typecheck, unit, component, accessibility và production build đạt.

## Checkpoint

- Route groups, dynamic nonce-compatible root boundary, server-only typed API client,
  semantic design tokens/primitives and deterministic test toolchain are complete.
- Experience review findings for skip navigation, duplicate accessible IDs,
  keyboard/focus, axe and narrow reflow are resolved.
- Security review findings for enforced nonce CSP and exact Server Action origin
  validation are resolved.
- Residual dependency risk: current latest Next.js 16.2.11 still bundles
  vulnerable PostCSS/Sharp versions reported by `npm audit`. Exploitability is
  currently low because CSS is trusted build input and the portal accepts no
  untrusted images. Security Owner must review by 2026-08-07 and upgrade when a
  compatible Next release carries fixed transitives; `npm audit fix --force`
  must not be used because it proposes an invalid downgrade.
- Exact next action: VFBIZ-0070 and VFBIZ-0071 implement the approved journeys
  on separate feature paths.

## Evidence

- [x] `npm run verify:apps` passed for Customer and Workforce portals.
- [x] Customer lint, typecheck, 7 unit tests, 2 component/a11y tests,
      9 Redis integration tests and production build passed after review fixes.
- [x] Playwright foundation acceptance passed 2/2 with
      `CUSTOMER_CSP_ENFORCE=true`, including axe, skip-link, reflow and CSP checks.
- [x] Experience/accessibility and security reviews completed within one fix cycle.
