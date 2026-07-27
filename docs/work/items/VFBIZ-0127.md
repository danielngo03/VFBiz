---
id: VFBIZ-0127
title: Wire postgres-spec integration tests into a real CI gate
status: proposed
mode: controlled
priority: P1
owner_team: api-foundation
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/package.json
  - backend/api/test/integration
  - backend/api/test/jest-postgres.json
  - backend/api/src/modules/customer
  - .github/workflows/foundation-quality.yml
  - docs/work/items/VFBIZ-0017.md
  - docs/work/items/VFBIZ-0018.md
  - docs/work/items/VFBIZ-0065.md
  - docs/work/items/VFBIZ-0127.md
depends_on: []
controlled_signals:
  - test-coverage
  - customer-conversation
  - customer-data
exclusive_resources: []
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 1
review_date: "2026-07-26"
---

# Outcome

Every `backend/api/test/integration/**/*.postgres-spec.ts` file runs on every
PR via a real npm script/CI job against a migrated PostgreSQL database, so a
regression in one is caught automatically instead of silently rotting.

## Constraints

- Không đổi nội dung test hiện có trừ khi nó thật sự sai; mục tiêu ở đây là
  wiring, không phải viết lại coverage.
- Không âm thầm nới lỏng assertion để "làm cho xanh" — nếu một suite fail khi
  wired vào CI, đó là bug cần fix (xem VFBIZ-0056's `conversation-runtime`
  finding), không phải lý do để xoá/skip test.

## Done when

- A real npm script (e.g. `test:integration:postgres`) runs
  `NODE_OPTIONS=--experimental-vm-modules jest --config
  test/integration/access/jest-postgres.json` (or a renamed/relocated
  equivalent covering all workspaces' `*.postgres-spec.ts` files, not just
  `access/`) against `VFBIZ_TEST_DATABASE_URL`.
- CI actually invokes that script against a real, migrated Postgres service,
  gating merges — not just documented as a local-only command.
- All currently-existing `*.postgres-spec.ts` suites pass once wired in, or
  have a tracked, accepted fix (see the `conversation-runtime` failure noted
  below).

## Checkpoint

- **Discovered while verifying VFBIZ-0056's idempotency work**: no npm
  script, `package.json` entry, or `.github/workflows/*.yml` file references
  `test/integration/access/jest-postgres.json` or
  `VFBIZ_TEST_DATABASE_URL` anywhere in the repo (confirmed by repo-wide
  grep). `npx jest --listTests` under the default config
  (`package.json`'s `testMatch: ["**/*.spec.ts", ...]`) returns zero
  `*.postgres-spec.ts` files — the naming convention
  (`name.postgres-spec.ts`) doesn't match `*.spec.ts` at all (the character
  before `spec.ts` is `-`, not `.`). This is the same class of gap as
  `backend/ai`'s `VFBIZ_RUN_DB_INTEGRATION` flag (VFBIZ-0114/0094 checkpoints)
  — a real-Postgres test suite that silently never runs, giving false
  confidence — except here it's worse: those AI tests at least show as
  `skipped`; these API ones aren't even collected, so there's no visible
  signal anything is missing.
- **`conversation-runtime.postgres-spec.ts` root-caused and fixed** (was
  "not yet root-caused" as of the previous checkpoint entry above). Two
  independent bugs, the first masking the second:
  1. `PrismaConversationRuntimeRepository`'s `getSnapshot`/
     `findAcceptedMessage`/`getTurnExecutionContext`/`listPublicEvents`/
     `commit` all called `new Date()` directly instead of accepting the
     caller's `ConversationRuntimeClock` value, so session-readability
     checks used real wall-clock time — meaning the test's hardcoded
     `2026-07-25`/`2026-07-26` fixture dates were guaranteed to start
     failing once real time passed them (a "time bomb", not flakiness).
     Fixed by adding `now: Date` to the abstract
     `ConversationRuntimeRepository` interface and threading
     `this.clock.now()` through every call site (`ConversationRuntimeService`,
     plus new clock-injection in `ConversationTurnDispatcher` and
     `ExecuteConversationTurnService`, both already covered by the existing
     `ConversationRuntimeClock` provider in `engagement-runtime.module.ts`).
  2. `updateTurn`'s claim-field handling had a
     `turn.status === 'cancelled' ? {} : {...}` special case that sent an
     *empty* payload on cancellation, so `workerId`/`fencingToken`/
     `leaseExpiresAt` were never cleared — silently violating the
     `conversation_turn_claim_shape_check` migration constraint (requires
     all three `NULL` once `status <> 'claimed'`). Unreachable until bug #1
     was fixed, since bug #1 caused an earlier `version-conflict` return
     first. Fixed by removing the special case; the domain aggregate
     already sets `claim: null` on cancellation, so the existing
     `turn.claim?.field ?? null` pattern now handles every status
     uniformly. One test assertion that expected the pre-bug (incorrect)
     retained `fencingToken` was corrected to assert the constraint-
     compliant `null`.
  - Full detail recorded on the owning items: VFBIZ-0017 (interface/clock)
    and VFBIZ-0018 (persistence adapter + constraint), both `status: done`
    — these are post-completion regression notes on already-accepted work,
    not new scope.
- **CI wiring done, not just documented**:
  - Moved `test/integration/access/jest-postgres.json` →
    `test/jest-postgres.json` (fixed `rootDir` accordingly) — it always
    covered every workspace's `*.postgres-spec.ts` file via
    `testRegex: "test/integration/.*\\.postgres-spec\\.ts$"`, so the old
    location under `integration/access/` was misleading.
  - Added `"test:integration:postgres"` to `backend/api/package.json`.
  - Added an `api-postgres-integration` job to
    `.github/workflows/foundation-quality.yml`, mirroring the existing
    `ai-postgres-integration` job's pattern exactly (a real
    `postgis/postgis:17-3.4` service container, `prisma migrate deploy`,
    then the new test script) — this is the first time backend/api's
    postgres-spec tests will actually run in CI.
- **Higher-severity finding, same root class, found while reviewing my own
  new job — `node-foundation` (the primary gate for the whole monorepo) had
  the identical missing-step bug, at much greater blast radius**. An
  independent reviewer flagged (without finishing the check) that
  `--ignore-scripts` on `npm ci` skips any package-level `postinstall`
  generation hook. Verified directly: `src/generated/` is gitignored (no
  committed client), neither `@prisma/client` nor `prisma`'s own
  `package.json` declares a `postinstall` that would generate it, and
  no workspace `package.json` has a `pretest`/`prebuild` hook that would
  either. Confirmed empirically — moved the real `src/generated` aside,
  ran `npm run build` (part of `verify:api`, part of `node-foundation`):
  **186 TypeScript errors**, a total build failure. `prisma generate`
  needs no database connection (verified separately with
  `VFBIZ_DATABASE_URL` unset), so this was a pure missing-step bug, not a
  database-availability one. In a genuinely fresh CI checkout (no
  locally-cached generated client from a prior run), `node-foundation` —
  and therefore `verify:governance`/`verify:api`/`verify:apps`/`npm audit`,
  i.e. essentially the entire monorepo's PR gate — would fail this same
  way. Fixed by adding `npm run prisma:generate --workspace @vfbiz/api`
  right after `npm ci --ignore-scripts` in both `node-foundation` and the
  new `api-postgres-integration` job. Restored the real generated client
  from a backup and re-ran `npm run lint`/`typecheck`/`test`/`verify:api`
  to confirm the working tree was left in a clean, fully passing state
  after the test.
  - This is a `docs/work/items/VFBIZ-0017.md`/`VFBIZ-0018.md`-style
    "post-completion regression" but on CI infrastructure itself rather
    than a specific work item's code — recorded here since this item is
    already the one touching `foundation-quality.yml`. Whether
    `node-foundation` has *ever* successfully completed in real GitHub
    Actions (as opposed to always failing, unnoticed, on this exact step)
    is unverified from this environment (no `gh` CLI access) — Engineering
    Lead should check the Actions run history to confirm impact.
- **Unrelated bug found and fixed while adding VFBIZ-0065's audit
  integration test** (same investigation pass, different repository):
  `PrismaWorkforceCustomerSupportRepository.search()` unconditionally
  included `{ id: { equals: input.query } }` in its filter; since `id` is
  a native Postgres `uuid` column, any non-UUID search term — i.e. every
  ordinary customer-name search, the primary use case — made Postgres
  reject the whole query outright ("invalid input syntax for type uuid"),
  a 500 on the single most common workforce search. Fixed by only
  including the exact-ID branch when the term is syntactically a UUID.
  Full detail on `docs/work/items/VFBIZ-0065.md`.
- **Related but separate finding, not fixed here**: `npm run test:migrations`
  (`scripts/verify-migrations.sh`) hardcodes a macOS Homebrew Postgres path
  (`/opt/homebrew/opt/postgresql@17/bin`) and a local port — it cannot run
  on the `ubuntu-latest` GitHub Actions runners `foundation-quality.yml`
  uses at all. Every work item's Evidence line for this required check
  (e.g. VFBIZ-0018, VFBIZ-0056) was necessarily satisfied by a human or
  agent running it locally, never by CI. Worth its own follow-up item
  (rewrite for a portable Postgres service container, or accept it as
  local-only and remove it from `required_checks`) — out of scope for this
  item, which is specifically about the `*.postgres-spec.ts` Jest suites.
- Exact next action: none blocking this item's own "Done when." Engineering
  Lead should (a) confirm via GitHub's Actions run history whether
  `node-foundation` has been silently failing, and (b) decide on the
  separate `test:migrations` portability gap noted above.

## Evidence

- [x] `npm run governance:check` — 2026-07-27: passed.
- [x] All 8 `*.postgres-spec.ts` suites (34 tests, including the new
  `workforce-customer-support.postgres-spec.ts`) pass via
  `VFBIZ_TEST_DATABASE_URL=... npm run test:integration:postgres
  --workspace @vfbiz/api` against a real, freshly migrated PostgreSQL 17 +
  PostGIS container — 2026-07-27.
- [x] `npm run verify:api` (lint, typecheck, 263 unit/integration tests, 63
  E2E tests, Prisma validation, Nest build) — 2026-07-27: passed, including
  a from-scratch re-run after temporarily removing and restoring the
  generated Prisma client to prove the `node-foundation` fix.
- [x] `.github/workflows/foundation-quality.yml` YAML syntax validated
  (`js-yaml` parse) and job structure confirmed for both
  `node-foundation` and `api-postgres-integration` — 2026-07-27.
