---
id: VFBIZ-0129
title: Remediate Node.js supply-chain advisories
status: active
mode: controlled
priority: P1
owner_team: api-foundation
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
  - .github/workflows/foundation-quality.yml
  - .github/workflows/security-assurance.yml
  - .github/dependabot.yml
  - docs/work/items/VFBIZ-0129.md
depends_on: []
controlled_signals:
  - supply-chain
  - security
exclusive_resources:
  - lockfile
required_checks:
  - npm audit --omit=dev --audit-level=high
  - npm run verify:api
  - npm run verify:apps
  - npm run verify:governance
revision: 7
review_date: "2026-07-27"
updated_at: "2026-07-27T17:00:18.329Z"
---

# Outcome

Remediate actionable Node.js production dependency advisories with pinned,
reviewed upgrades or narrowly scoped overrides, without broad `npm audit fix`
rewrites.

## Constraints

- The lockfile is exclusive while this work item is active.
- Upgrade only an advisory's direct dependency chain; major upgrades require
  the relevant API or portal verification gate.
- Do not suppress an advisory, lower the audit threshold, or use an unpinned
  registry mirror as a substitute for remediation.

## Done when

- Production audit has no unaccepted high or critical advisory.
- API and both portal verification gates prove compatibility after the lockfile
  update.
- The CI dependency audit reports actionable detail. Repository branch
  protection may call it a merge gate only after the external required-check
  configuration has been verified.

## Checkpoint

- Updated OpenTelemetry auto-instrumentation and both portals to the current
  compatible patch releases. API, Customer Portal and Workforce Portal gates
  passed after the update.
- A direct upgrade of `@fastify/static` to 10.1.2 was rejected by the NestJS
  Swagger contract test: NestJS 11's current package loader treated that
  package as unavailable. The manifest/lockfile were restored to the supported
  9.3.0 line; no force override was retained.
- Local security commands and the intended CodeQL, secret scan, Python audit,
  filesystem/image scan and SBOM controls are documented, but this solo
  direct-main repository currently has no committed `.github` workflow.
  Therefore CI enforcement is **not implemented** and must not be claimed.
- Dependabot automation is not active. Dependency review remains a manual
  release gate until a staging/PR workflow is explicitly introduced.
- `npm audit --omit=dev` still reports vendor-chain findings pinned by current
  NestJS/Prisma/Next dependency metadata, including `find-my-way`, `js-yaml`,
  `postcss` and `sharp`: 15 high and 1 moderate finding on 2026-07-27. The
  registry's proposed "fix" versions are in several cases lower than the
  installed current package and are not a safe automated remediation.
- Prisma client/adapter/CLI được nâng đồng bộ từ 7.9.0 lên 7.9.1; advisory của
  `prisma`/`@prisma/dev` đã biến mất. Production audit hiện còn 14 high, không
  còn moderate/critical. API 330 unit + 67 E2E và hai portal production build
  tiếp tục đạt. Thử nghiệm `@fastify/static` 10.1.2 tiếp tục xác nhận không
  tương thích peer/runtime loader của NestJS 11 nên đã được phục hồi về 9.3.0.
- Exact next action: Security Owner reviews the vendor advisories against the
  affected deployment paths and either accepts documented residual risk with
  compensating controls or approves a framework upgrade program. Do not use
  `npm audit fix --force`.

## Evidence

- [ ] `npm audit --omit=dev --audit-level=high` — still blocked by current
      NestJS/Prisma/Next vendor chains; no force downgrade or suppression used
- [x] `npm run verify:api` — 330 unit, 67 E2E, typecheck và build passed after Prisma 7.9.1
- [x] `npm run verify:apps` — Customer và Workforce lint/typecheck/test/integration/build passed with Next.js 16.2.12
- [x] `npm run verify:governance` — passed for repository governance; this is
      not evidence of hosted CI enforcement

### active — 2026-07-27T03:57:58.985Z

Checkpoint recorded; add observed state and one exact next action.

### active — 2026-07-27T17:00:18.329Z

Prisma 7.9.1 remediation passed API and portal regression; production audit reduced to 14 high with no moderate/critical. Remaining vendor-chain advisories have no compatible upstream release and remain Security Owner blocked.
