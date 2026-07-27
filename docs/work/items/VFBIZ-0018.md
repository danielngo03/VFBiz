---
id: VFBIZ-0018
title: Conversation Runtime persistence integration
status: done
mode: controlled
priority: P0
owner_team: customer-engagement
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/prisma/models/engagement.prisma
  - backend/api/prisma/migrations
  - backend/api/src/modules/engagement/domain/runtime
  - backend/api/src/modules/engagement/application/ports
  - backend/api/src/modules/engagement/application/runtime
  - backend/api/src/modules/engagement/application/services
  - backend/api/src/modules/engagement/infrastructure
  - backend/api/src/modules/engagement/engagement.module.ts
  - backend/api/src/modules/engagement/presentation
  - backend/api/test/e2e/engagement
  - backend/api/test/integration/engagement
depends_on:
  - VFBIZ-0017
  - VFBIZ-0032
  - VFBIZ-0086
controlled_signals:
  - customer-conversation
  - session-concurrency
  - migration
  - schema
  - pii
exclusive_resources:
  - database-migration
required_checks:
  - npm run test:migrations --workspace @vfbiz/api
  - npm run verify:api
revision: 10
review_date: "2026-08-23"
updated_at: "2026-07-24T18:03:02.568Z"
---

# Outcome

Persistence của Conversation Runtime được triển khai bằng migration có replay,
constraint/index và recovery evidence phù hợp với application core VFBIZ-0017.

API Foundation phối hợp review migration/transaction strategy; Customer
Engagement vẫn là owner duy nhất của schema và persistence adapter trong bounded
context này.

## Constraints

- Chỉ integration owner ghi migration và giữ `database-migration` lease.
- Một scoped writer với role `integrator` sở hữu atomic change gồm schema,
  persistence adapter và migration; API Foundation review migration/replay ở
  chế độ read-only, không trở thành writer thứ hai.
- Không đổi public/AI contract trong lane này.
- Legacy conversation projection không được backfill bằng identity, citation
  hoặc source giả.
- Durable inbox không lưu raw message; content phải dùng authenticated
  encryption primitive từ `VFBIZ-0086`, pin key revision và purge cùng subject.

## Done when

- Clean database và legacy fixture áp toàn bộ migration không drift.
- Unique/partial index bảo vệ idempotency, monotonic sequence, active claim và
  handoff lifecycle như schema cho phép.
- Migration fail closed khi dữ liệu legacy không thể chuyển an toàn.
- PostgreSQL integration test chứng minh transaction, OCC/fencing và purge.
- Mỗi conversation chỉ có một active turn; message đến sau được giữ trong
  durable inbox và claim bằng lease/fencing token.
- Duplicate/out-of-order message, stale claim, cancellation và late result
  không thể ghi đè version mới.
- Existing message history decrypts only after a scope-bound authorization
  decision; encrypted content never falls back to an empty successful result.
- Retention/DSAR purge rechecks eligibility inside the transaction and fences
  concurrent authenticated-session creation.

## Checkpoint

- Persistence runtime đã hoàn tất với encrypted content/fingerprint, canonical
  AAD, durable inbox, OCC/fencing, cancellation authority riêng theo trusted
  entrypoint, encrypted history, DSAR fence và retention purge có lock order
  thống nhất.
- Migration backfill `ownerSubjectKeyHash` cho authenticated legacy session
  bằng cùng length-framed SHA-256 contract; migration fail closed nếu còn owner
  chưa ánh xạ.
- Exact next action sau khi đóng work item: VFBIZ-0019 triển khai public command
  và SSE contract trên persistence boundary này, không mở rộng scope VFBIZ-0018.

## Evidence

- [x] `npm run test:migrations --workspace @vfbiz/api` — PostgreSQL
  17/PostGIS clean replay, legacy replay, schema drift và 24 integration tests
  đạt ngày 2026-07-25.
- [x] `npm run verify:api` — lint, typecheck, 44 unit suites/220 tests,
  9 E2E suites/61 tests, Prisma validation và NestJS build đạt ngày 2026-07-25.
- [x] `npm run verify:governance` — 83 WorkItemV2, 61 provider-neutral context
  scenarios, report drift và toàn bộ OpenAPI contracts đạt ngày 2026-07-25.
- [x] Independent review — hai vòng review/fix đã xử lý replay confidentiality,
  AAD, cancellation authority, DSAR legacy coverage, retention lock order,
  strict event decoding, encrypted history và citation storage limits.

## Residual risks

- Subject owner key hiện là pseudonymous SHA-256 framed digest để tương thích
  migration SQL. Chuyển sang keyed token cần migration/rotation riêng và Privacy
  Owner phê duyệt, không đổi âm thầm trong runtime.
- Citation projection giữ metadata nguồn ở dạng queryable plaintext; source URI
  nhạy cảm hoặc signed URI phải được chặn tại Knowledge contract hoặc mã hóa ở
  work item riêng.
- Forced deadlock/fault-injection sâu hơn thuộc resilience suite; implementation
  hiện dùng global lock order, serializable transaction và retry hữu hạn.

### review hardening — 2026-07-24T17:46:57.755Z

Independent review found P1 gaps in replay-fingerprint confidentiality,
canonical AAD, cancellation authority, purge concurrency, strict event decoding
and encrypted history reads. Scope expanded only to the existing conversation
presentation boundary required for an authorized history response.

### blocked — 2026-07-24T17:23:12.733Z

Needs VFBIZ-0086 content protection configuration before durable inbox persistence

### post-completion regression note — 2026-07-27

Found while investigating VFBIZ-0127 (postgres-spec tests never wired into
CI, so these went undetected — the 24 integration tests referenced in this
item's own Evidence above were run manually at the time, not by any
standing gate). Two real bugs in
`PrismaConversationRuntimeRepository`, both now fixed:

1. `getSnapshot`/`findAcceptedMessage`/`getTurnExecutionContext`/
   `listPublicEvents`/`commit` (via its private `commitTransaction` helper)
   all called `new Date()` directly for session-readability checks instead
   of accepting the caller's `ConversationRuntimeClock` value — see the
   matching note on VFBIZ-0017, which owns the interface-level fix.
2. `updateTurn`'s claim-field handling had a `turn.status === 'cancelled'
   ? {} : {...}` special case that sent an *empty* claim payload on
   cancellation — meaning `workerId`/`fencingToken`/`leaseExpiresAt` were
   never cleared in the database, silently violating this migration's own
   `conversation_turn_claim_shape_check` constraint (which requires all
   three to be `NULL` once `status <> 'claimed'`). The domain aggregate
   (VFBIZ-0017) already correctly sets `claim: null` on cancellation; the
   fix removes the special case entirely so `updateTurn` clears all three
   fields via the same `turn.claim?.field ?? null` pattern already used for
   every other status. This was previously unreachable in practice because
   bug #1 caused an earlier `version-conflict` return before this code path
   was ever exercised — bug #1 was masking bug #2.

Re-verified: `npm test` (263), `npm run test:e2e` (63), all 30
`*.postgres-spec.ts` tests against a real, freshly migrated PostgreSQL 17 +
PostGIS container, lint, typecheck, `prisma:validate`, `test:migrations` —
all pass as of 2026-07-27.
