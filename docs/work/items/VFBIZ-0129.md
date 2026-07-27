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
revision: 5
review_date: "2026-07-27"
updated_at: "2026-07-27T08:36:00.000Z"
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
- GitHub Actions in the foundation workflow are pinned to immutable commit
  SHAs; PostgreSQL/PostGIS service images are pinned to observed registry
  digests instead of mutable tags.
- Added a separate security-assurance workflow with pinned CodeQL,
  Gitleaks, Python dependency audit, Trivy filesystem/misconfiguration scan
  and independently retained SPDX SBOM generation. Trivy reports unfixed
  findings rather than suppressing them. Local `pip-audit` over the frozen AI
  dependency export reports no known vulnerability.
- Dependabot now proposes bounded weekly npm and GitHub Actions updates; these
  remain subject to the same verification and human review gates.
- `npm audit --omit=dev` still reports vendor-chain findings pinned by current
  NestJS/Prisma/Next dependency metadata, including `find-my-way`, `js-yaml`,
  `postcss` and `sharp`: 15 high and 1 moderate finding on 2026-07-27. The
  registry's proposed "fix" versions are in several cases lower than the
  installed current package and are not a safe automated remediation.
- Exact next action: Security Owner reviews the vendor advisories against the
  affected deployment paths and either accepts documented residual risk with
  compensating controls or approves a framework upgrade program. Do not use
  `npm audit fix --force`.

## Evidence

- [ ] `npm audit --omit=dev --audit-level=high` — still blocked by current
      NestJS/Prisma/Next vendor chains; no force downgrade or suppression used
- [x] `npm run verify:api` — passed after supported dependency restoration
- [x] `npm run verify:apps` — passed with Next.js 16.2.12 in both portals
- [x] `npm run verify:governance` — passed after workflow pinning

### active — 2026-07-27T03:57:58.985Z

Checkpoint recorded; add observed state and one exact next action.
