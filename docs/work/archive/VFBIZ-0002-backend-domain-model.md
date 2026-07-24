---
id: plan-vfbiz-0002
title: Backend domain model implementation plan
status: archived
owner_role: engineering-lead
scope: backend
when_to_read:
  - backend-domain-model
tags:
  - plan
  - backend
revision: 1
review_date: 2026-07-22
supersedes: []
---

# Backend Domain Model and Agent Operations Implementation Plan

Use the current work item and nearest workspace instructions. This historical
plan does not authorize implementation by itself.

**Goal:** Close the staging-critical persistence gaps in the NestJS API and make backend capability changes repeatable, provider-neutral and correctly governed.

**Architecture:** Keep the approved NestJS/Fastify modular monolith and private FastAPI service. Expand only the `access`, `customer`, `product`, `mobility`, `engagement`, `operations` and platform records required by the approved account/chat/trip staging slice; leave sales, ownership and commerce projections unchanged until their PRDs are approved. Add one canonical backend-capability skill and machine-readable department/team ownership instead of creating role or provider copies.

**Tech Stack:** NestJS 11, Fastify, Prisma 7 multi-file schema, PostgreSQL/PostGIS, Jest, Node governance validators, Agent Skills.

## Global Constraints

- `backend/api` remains the only public API and business transaction authority.
- `backend/ai` remains private and never owns customer sessions or business side effects.
- Do not store credentials, MFA secrets, raw VIN, raw Google responses, embeddings, prompts, payment card data or production PII in API PostgreSQL.
- Existing applied migration files are immutable; every schema change uses a new additive migration.
- Public contract, migration, lockfile, Drupal config and AI dataset registry are exclusive-write resources.
- A bounded task uses one implementer by default; controlled work adds only the relevant verifier/reviewer.
- Canonical rules live once in `AGENTS.md`, docs, JSON schema or `SKILL.md`; provider adapters contain mechanics only.

---

### Task 1: Correct controlled-change routing and add the backend capability skill

**Files:**
- Modify: `tools/lib/governance.mjs`
- Modify: `tests/governance/scenarios.json`
- Create: `.agents/skills/evolve-backend-capability/SKILL.md`
- Modify: `.agents/organization.json`

**Interfaces:**
- Consumes: `resolveContext(input)` and current governance V2 envelopes.
- Produces: deterministic `schema`, `migration` and `public-contract` classification plus the `evolve-backend-capability` workflow.

- [ ] **Step 1: Preserve the observed RED pressure test**

Run:

```bash
npm run context:resolve -- --stage delivery \
  --path backend/api/prisma/models/customer.prisma \
  --request "Thêm Prisma schema, migration, NestJS use case và OpenAPI"
```

Expected before the fix: incorrect `bounded` routing or missing `database-migration`/`public-contract` leases.

- [ ] **Step 2: Infer controlled signals from real paths and request language**

Treat `backend/api/prisma/**/*.prisma` as `schema`, `prisma/migrations/**` as `migration`, and root public OpenAPI as `public-contract`. API capability evolution must select `evolve-backend-capability` and `verify-change`, while claim/integration stages retain their dedicated skills.

- [ ] **Step 3: Add one canonical skill**

The skill must stop without the required Git-native claim and lease, map the change to an existing bounded context, decide contract compatibility, require a migration/backfill strategy, preserve four-layer boundaries, run focused checks and publish evidence. It must not contain provider-specific commands.

- [ ] **Step 4: Update affected golden scenarios**

Update the additive contract, breaking contract and zero-downtime migration expectations. Keep 32 scenarios and provider-invariant routing.

- [ ] **Step 5: Verify governance**

Run:

```bash
npm run context:resolve -- --stage delivery \
  --path backend/api/prisma/models/customer.prisma \
  --path backend/api/prisma/migrations/20260722190000_staging_domain_integrity/migration.sql \
  --request "Thêm Prisma schema, migration và OpenAPI"
npm run test:governance
```

Expected: `controlled`, `schema` + `migration`, `database-migration`, the new skill, and all governance checks passing.

### Task 2: Represent departments, leads, teams and authority routing without role explosion

**Files:**
- Modify: `contracts/governance/organization.schema.json`
- Modify: `.agents/organization.json`
- Modify: `tools/check-agent-governance.mjs`
- Create: `docs/operating-model/department-and-team-topology.md`
- Modify: `docs/catalog.json`

**Interfaces:**
- Consumes: the existing eight generic execution roles and workspace ownership.
- Produces: `departments[]`, `teams[]` and `authorityRouting` references that are validated and provider-neutral.

- [ ] **Step 1: Add failing organization-reference validation**

The validator must reject a team whose `departmentId` does not exist, a department whose `leadHumanRole` is not in `humanAuthorities`, duplicate IDs, unknown workspace IDs and an authority route referencing an unknown human authority.

- [ ] **Step 2: Add logical organization topology**

Declare Product & Delivery, Architecture & Risk, Engineering Enablement, Digital Platform, AI & Data, Web Experience, Client Experience, Operations Applications and Platform/SRE. Each department has one accountable human lead role; teams own capability/path boundaries. Do not create an agent role for every job title.

- [ ] **Step 3: Document runtime behavior**

State that the organization hierarchy assigns accountability, while runtime execution stays shallow: one orchestrator, at most three direct specialists, one writer per path, and no worker spawning another worker.

- [ ] **Step 4: Validate**

Run `npm run governance:check` and expect organization, catalog, role and provider-adapter validation to pass.

### Task 3: Add staging-critical API persistence models and provenance

**Files:**
- Modify: `backend/api/prisma/models/platform.prisma`
- Modify: `backend/api/prisma/models/access.prisma`
- Modify: `backend/api/prisma/models/customer.prisma`
- Modify: `backend/api/prisma/models/product.prisma`
- Modify: `backend/api/prisma/models/mobility.prisma`
- Modify: `backend/api/prisma/models/engagement.prisma`
- Modify: `backend/api/prisma/models/operations.prisma`
- Test: `backend/api/test/architecture/prisma-schema.spec.ts`

**Interfaces:**
- Consumes: the approved staging contracts for account, garage, customer chatbot and deterministic trip planning.
- Produces: source-governed projections and immutable workflow/audit records; no new top-level bounded context.

- [ ] **Step 1: Write schema contract tests**

Require models for customer data requests, source governance, conversation citations, read-only tool proposals, support handoff and independent release decisions. Require session lifecycle, garage integrity, trip algorithm revision and charging freshness fields.

- [ ] **Step 2: Expand source governance**

Add owner, provenance URI, license identifier, classification, approval state and refresh/freshness policy to `SourceRevision`. Add explicit source relations where a projection has exactly one authoritative revision.

- [ ] **Step 3: Expand account and customer persistence**

Add `lastSeenAt`, device label and provider session reference to session projection. Add `CustomerDataRequest`. Align garage fields with the public contract (`vehicleModelId`, required `vehicleVariantId`, `displayName`, verification timestamps/reason) while storing only token references for VIN.

- [ ] **Step 4: Expand mobility persistence**

Add charging connector provider reference/count/observation time, tariff session/idle fees and tax metadata, energy schema/algorithm revisions, and typed trip request/status/provider/cache-policy metadata. Keep provider payloads out of storage.

- [ ] **Step 5: Expand governed engagement and release audit**

Add session capability/expiry, message sequence/outcome/AI release revision, normalized citation evidence, validated read-only tool proposal records, support handoff and immutable release-decision events.

- [ ] **Step 6: Format and validate Prisma**

Run:

```bash
npm run prisma:format --workspace @vfbiz/api
npm run prisma:validate --workspace @vfbiz/api
npm run prisma:generate --workspace @vfbiz/api
```

Expected: schema formatting, validation and client generation pass without provider credentials.

### Task 4: Add an additive migration and database evidence

**Files:**
- Create: `backend/api/prisma/migrations/20260722190000_staging_domain_integrity/migration.sql`
- Modify: `backend/api/test/integration/platform/postgres-foundation.spec.ts`

**Interfaces:**
- Consumes: Task 3 Prisma schema.
- Produces: forward-only staging migration with indexes, foreign keys and immutable event records.

- [ ] **Step 1: Generate migration SQL against an isolated disposable PostgreSQL/PostGIS database**

Do not edit `20260722160000_platform_foundation/migration.sql`. Review every destructive statement; this additive change must not drop a table or column.

- [ ] **Step 2: Add migration integrity assertions**

Assert the new tables, source relations, owner indexes and trip/chat lifecycle indexes exist after deployment. Verify migration checksums and repeat deployment idempotence.

- [ ] **Step 3: Run disposable database tests**

Run the repository's PostgreSQL integration command and expect all migrations plus concurrency/outbox/idempotency tests to pass.

### Task 5: Add local backend documentation and one reusable work template

**Files:**
- Create: `backend/README.md`
- Create: `backend/api/docs/data-ownership-and-modeling.md`
- Create: `backend/api/docs/capability-implementation-template.md`
- Create: `backend/ai/docs/release-and-profile-boundaries.md`
- Modify: `backend/api/AGENTS.md`
- Modify: `backend/ai/AGENTS.md`
- Modify: `docs/catalog.json`

**Interfaces:**
- Consumes: approved runtime boundaries and model changes.
- Produces: a context-efficient documentation router and capability template; fields remain canonical in Prisma/OpenAPI rather than duplicated in prose.

- [ ] **Step 1: Write the backend router**

Explain when to enter API versus AI, shared invariants, contract ownership, and the minimum document set for a local task.

- [ ] **Step 2: Write API data ownership conventions**

Document owned data versus projections/references, source/freshness, JSON-versus-table rules, money/time/version/concurrency conventions, retention and migration ownership.

- [ ] **Step 3: Write the capability implementation template**

Include claim/lease, acceptance, bounded-context decision, domain/application/infrastructure/presentation files, authorization, transaction/outbox, migration, OpenAPI compatibility, SDK and evidence checklists. It is a template, not another source of product truth.

- [ ] **Step 4: Write AI profile/release boundaries**

Document public/authenticated/employee profiles, namespace isolation, release manifest, evaluation, tool proposal and kill-switch ownership without repeating model fields.

- [ ] **Step 5: Register only active documents**

Add catalog metadata with valid owner roles, precise `whenToRead` triggers and review dates. Do not auto-load historical plans.

### Task 6: Verify, review and update delivery evidence

**Files:**
- Modify only if checks expose a defect in files from Tasks 1–5.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: observed evidence for the canonical work item; it does not claim staging or production release.

- [ ] **Step 1: Run API quality gates**

```bash
npm run lint --workspace @vfbiz/api
npm run typecheck --workspace @vfbiz/api
npm test --workspace @vfbiz/api -- --runInBand
npm run test:e2e --workspace @vfbiz/api -- --runInBand
npm run build --workspace @vfbiz/api
```

- [ ] **Step 2: Run governance gates**

```bash
npm run test:governance
```

- [ ] **Step 3: Review scoped diff**

Confirm no credential/PII/raw provider response, no new top-level business context, no framework import in domain code, no destructive migration and no provider-specific policy duplication.

- [ ] **Step 4: Publish work-item evidence**

Update the work-item checkpoint with changed paths, migration revision, observed commands, residual gaps and next action. Keep the item in `review` until staging acceptance and human approval exist.
