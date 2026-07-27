---
id: VFBIZ-0056
title: Workforce authorization runtime and API
status: active
mode: controlled
priority: P0
owner_team: api-foundation
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/access
  - backend/api/src/platform/security
  - backend/api/prisma/models/access.prisma
  - backend/api/prisma/migrations
  - backend/api/prisma/seed
  - backend/api/scripts/bootstrap-workforce-administrators.ts
  - backend/api/package.json
  - backend/api/test/e2e/access
  - backend/api/test/integration/access
  - backend/api/docs/workforce-authorization.md
  - contracts/openapi/workforce-v1.yaml
  - docs/work/items/VFBIZ-0056.md
  - docs/work/plans/VFBIZ-0055.md
  - WORK.md
depends_on:
  - VFBIZ-0055
controlled_signals:
  - authorization
  - workforce-admin
  - migration
exclusive_resources:
  - database-migration
  - public-contract
required_checks:
  - npm run verify:api
  - npm run test:migrations --workspace @vfbiz/api
  - npm run governance:check
revision: 3
review_date: "2026-08-24"
updated_at: "2026-07-24T20:10:00.000+07:00"
---

# Outcome

API resolve dynamic workforce entitlement từ PostgreSQL, enforce capability
deny-by-default và expose workforce authorization management contract.

## Constraints

- Không tin business role/capability từ token.
- Capability catalog là contract code-owned.
- Scope chỉ global, market, showroom hoặc department.
- Privileged change bắt buộc maker-checker và step-up MFA.
- Mutation, audit, revision và outbox atomic.

## Done when

- Additive schema/migration và seed catalog hợp lệ.
- Capability decorator/decision service có negative tests.
- Workforce API có role, assignment, approval và entitlement baseline.
- Redis chỉ là optional cache; database failure fail closed.

## Checkpoint

- Implemented capability/role/assignment/approval schema and additive migration.
- Added database-backed entitlement resolution, capability decision service,
  deny-by-default guard and workforce management endpoints.
- Added separate workforce OpenAPI contract and local authorization boundary
  documentation.
- Added directory projection and minimized audit query endpoints; repository
  prevents revoking the final active global authorization administrator.
- Added controlled, non-HTTP two-administrator bootstrap with an explicit
  acknowledgement, audit/outbox evidence and partial-authority refusal.
- **Done, real, tested — durable idempotency replay is wired for all 8
  mutation endpoints** on `WorkforceAuthorizationController` (createRole,
  updateRole, replaceCapabilities, createAssignment, revokeAssignment,
  createChangeRequest, approveChangeRequest, rejectChangeRequest). The
  `IdempotencyRecord` Prisma model existed but had zero callers anywhere in
  `src`; `requireIdempotencyKey()` only regex-validated the header without
  ever persisting or replaying. Added `IdempotencyRepository` port +
  `PrismaIdempotencyRepository` (namespace-scoped per operation,
  request-hash-bound to the exact payload/path params, serializable
  transaction + retry matching the existing
  `withSerializableRetry`/`isRetryableTransactionError` pattern from
  `prisma-customer-garage.repository.ts`). A retried mutation with the same
  key+body now replays the cached response instead of re-executing; the
  same key with a different body or a still-in-flight duplicate gets a 409
  `IDEMPOTENCY_KEY_CONFLICT`, never a silent pass-through. Unexpected
  (non-domain) errors are deliberately not cached, so a corrected retry can
  still succeed.
- **Verification note**: `backend/api`'s `*.postgres-spec.ts` integration
  tests (including the new `idempotency.postgres-spec.ts`, 6 tests) are not
  invoked by `npm test`, `npm run test:e2e`, or any CI workflow — only a
  standalone `test/integration/access/jest-postgres.json` config exists,
  unreferenced anywhere. Ran manually against a real, freshly migrated
  PostgreSQL container
  (`NODE_ENV=test VFBIZ_TEST_DATABASE_URL=... npx jest --config
  test/integration/access/jest-postgres.json`): all 6 new tests pass
  (fresh reserve, exact replay, conflict on reused key with different body,
  conflict on in-flight duplicate, only one winner under concurrent
  reservation, namespace isolation). Filed separately as VFBIZ-0127 — this
  item does not fix that wiring gap itself, since it's a pre-existing,
  repo-wide issue affecting every `*.postgres-spec.ts` file, not specific
  to idempotency.
- **Independent review surfaced 3 further defects in the idempotency
  mechanism itself** (reviewer-verifier pass over the durable-replay work
  above); all 3 fixed and re-verified:
  1. (Medium) `expiresAt` was write-only — nothing ever checked it, so the
     "24h TTL" in the code comment was fiction: a reservation whose
     `complete()` never ran (e.g. process crash between commit and
     `complete()`) stranded that Idempotency-Key forever with no recovery
     path. Fixed in `PrismaIdempotencyRepository.reserve()`: a `pending`
     (never-completed) record is now only a `conflict` while
     `expiresAt > now`; once elapsed, it is reclaimed in place (reset to
     `pending` with a fresh `expiresAt`, `responseStatus`/`responseBody`
     cleared) and returned as a fresh `reserved`, rather than conflicting
     indefinitely.
  2. (Medium) `operation()` and `complete()` were two separate statements
     with no atomicity between them — this is what made Finding 1 reachable
     in the first place (a crash between them left a permanently-`pending`
     row). Addressed by the same reclaim-on-expiry fix: since the failure
     mode is now self-healing after the TTL window instead of permanent,
     the lack of cross-statement atomicity no longer stalls the key
     forever. Full atomicity (e.g. writing the outcome inside the same
     transaction as the business mutation) would need a larger unit-of-work
     change across every one of the 8 call sites and was judged
     disproportionate to the actual risk once the reclaim path exists.
  3. (Low) Idempotency keys were namespace+key-scoped but not scoped to the
     authenticated principal, so two different workforce principals reusing
     the same `Idempotency-Key` header value and an identical body could in
     theory replay each other's cached response. Fixed by threading
     `principal.subject` into `idempotencyRequestHash(...)` as the first
     argument at all 8 call sites in `workforce-authorization.controller.ts`,
     so the hash — and therefore the conflict/replay decision — is now
     bound to `(principal, operation, payload)`, not just
     `(operation, payload)`.
  - New coverage added, not just fixed-and-trusted: `idempotency
    .postgres-spec.ts` gained a reclaim-on-expiry test (`ttlSeconds: -1`
    to deterministically simulate an already-elapsed TTL without a real
    sleep, asserting both the `reserved` outcome and that the row itself
    resets to `pending`/null response/a future `expiresAt`) — 35 tests in
    that suite family now, up from 34. `workforce-authorization
    .controller.spec.ts` is a new unit spec exercising the now-exported
    `idempotencyRequestHash` directly: same principal+body is deterministic,
    different principal+same body produces a different hash (the Finding 3
    regression test), different body changes the hash, and key order does
    not (canonical JSON) — 4 tests.
  - Exact next action on this finding set: none open. Full transactional
    atomicity for Finding 2 (option, not requirement) remains available as
    future hardening if a specific incident ever demonstrates the reclaim
    window is insufficient.
- **Correction to an earlier note in this Checkpoint**: this item's Done-when
  line ("Redis chỉ là optional cache; database failure fail closed") is a
  constraint on Redis *if used*, not a mandate that a Redis cache must be
  built. `authorization-decision.service.ts` reading Postgres directly, with
  no cache layer at all, satisfies this vacuously — there is no Redis in the
  critical path to fail closed *from*. An earlier Checkpoint entry called
  this "remaining work" ("Redis entitlement-invalidation transport remains
  undone"); on re-reading the actual Done-when text, that overstated the
  requirement and risked a future agent building speculative caching with no
  current performance justification. No code change needed for this line;
  correcting the record only.

## Evidence

- [x] Prisma format, validate and generate
- [x] API lint and typecheck
- [x] API build
- [x] Focused capability decision/decorator/guard tests (8 tests)
- [x] Workforce OpenAPI contract lint
- [x] PostgreSQL clean replay, schema drift, 17 integration tests and legacy backfill
- [x] API lint/typecheck, 197 unit/integration tests, 59 E2E tests, Prisma
  validation and build
- [x] `npm run test:migrations --workspace @vfbiz/api`
- [x] Bootstrap command fails closed without explicit acknowledgement.
- [x] Durable idempotency replay — 2026-07-27: `npm run lint`/`npm run
  typecheck`/`npm test` (263 tests)/`npm run test:e2e` (63 tests)/`npm run
  prisma:validate`, all `--workspace @vfbiz/api`, all pass; plus 6 new
  `idempotency.postgres-spec.ts` tests run manually against real Postgres
  (see Checkpoint note on the postgres-spec CI-wiring gap).
- [x] Idempotency review fixes (expiry-reclaim, principal-scoping) —
  2026-07-27: `npm run verify:api` (lint, typecheck, 267 unit/integration
  tests, 63 E2E tests, Prisma validation, Nest build) passes clean; all 8
  `*.postgres-spec.ts` suites (35 tests, via VFBIZ-0127's
  `test:integration:postgres`) pass against a real, freshly migrated
  PostgreSQL 17 + PostGIS container, including the new reclaim-on-expiry
  case.
- [ ] Redis entitlement-invalidation transport.
