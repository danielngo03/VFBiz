---
id: VFBIZ-0131
title: Remediate Node supply-chain release blockers
status: cancelled
mode: controlled
priority: P0
owner_team: architecture-integration
accountable_role: security-owner
primary_workspace: root
affected_workspaces:
  - root
  - api
  - customer-portal
  - workforce-portal
allowed_paths:
  - package.json
  - package-lock.json
  - backend/api/package.json
  - apps/customer-portal/package.json
  - apps/workforce-portal/package.json
  - packages/portal-session-core/package.json
  - docs/work/items/VFBIZ-0131.md
depends_on: []
controlled_signals:
  - dependency
  - security
  - production
exclusive_resources:
  - dependency-lockfile
required_checks:
  - npm run verify:api
  - npm run verify:apps
  - npm run governance:check
  - npm audit --omit=dev --audit-level=high
revision: 5
review_date: "2026-07-27"
updated_at: "2026-07-27T17:00:18.037Z"
---

# Outcome

Giảm toàn bộ Node high/critical supply-chain finding có bản vá tương thích,
không dùng force downgrade và ghi rõ residual finding chưa có upstream fix để
Security Owner quyết định trước staging.

## Constraints

- Không dùng `npm audit fix --force` hoặc downgrade framework để làm xanh số liệu.
- Lockfile là exclusive resource; mọi override phải trỏ tới patched upstream
  version và vượt API/portal regression.
- Next.js/sharp hoặc transitive package chưa có compatible upstream release
  không được tự chấp nhận rủi ro; ghi owner, mitigation và expiry riêng.
- Không thay đổi runtime behavior ngoài dependency remediation.

## Done when

- Direct package có compatible patched release được nâng và lockfile không còn
  invalid/overridden dependency graph.
- API và hai portal vượt lint, typecheck, unit/integration và production build.
- Audit output phân biệt remediated, unreachable development-only và residual
  production finding chưa có upstream fix.
- Không high/critical finding nào bị ignore bằng `.npmrc`, audit suppression
  hoặc undocumented exception.

## Checkpoint

- Exact next action: apply compatible patch releases, review lockfile diff and run regressions.

## Evidence

- [x] `npm run verify:api` — 330 unit tests, 67 E2E, lint, typecheck, Prisma validation and production build passed after Prisma 7.9.1 upgrade on 2026-07-27.
- [x] `npm run verify:apps` — Customer and Workforce lint, typecheck, unit/integration tests and both Next.js production builds passed on 2026-07-27.
- [x] `npm run governance:check` — docs/reports indexes, 128 work schemas and 72 context scenarios passed after lockfile changes on 2026-07-27.
- [ ] `npm audit --omit=dev --audit-level=high` — reduced 17 production findings (16 high, 1 moderate) to 14 high and zero moderate/critical. Remaining advisories have no compatible upstream release: NestJS 11 peers require `@fastify/static` 8/9 while patched 10.1.2 fails API contract runtime loading; current Next.js 16.2.12 is still inside the advisory range and pins vulnerable PostCSS/sharp; current NestJS Swagger pins js-yaml 5.2.1; OpenTelemetry GCP chain has no patched `gcp-metadata` release. No ignore or risk acceptance was added.

### blocked — 2026-07-27T16:59:35.386Z

Compatible Prisma patch remediation and regressions passed. Fourteen production high advisories remain because current NestJS/Next.js/OpenTelemetry dependency lines do not publish compatible patched releases; no ignore or risk acceptance was added. Recheck upstream releases before staging.

### cancelled — 2026-07-27T17:00:18.037Z

Cancelled as duplicate of active VFBIZ-0129; all observed dependency changes and audit evidence were consolidated into the canonical work item.
