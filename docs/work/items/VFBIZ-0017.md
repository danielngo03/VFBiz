---
id: VFBIZ-0017
title: Conversation Runtime application core
status: done
mode: controlled
priority: P0
owner_team: customer-engagement
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/engagement/application
  - backend/api/src/modules/engagement/domain
  - backend/api/src/modules/engagement/presentation
  - backend/api/src/modules/engagement/engagement.module.ts
  - backend/api/src/modules/engagement/index.ts
  - backend/api/docs/conversation-runtime.md
  - backend/api/test/e2e/engagement
  - backend/api/test/integration/engagement
depends_on:
  - VFBIZ-0016
controlled_signals:
  - customer-conversation
  - support-handoff
  - session-concurrency
  - pii
exclusive_resources: []
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 5
review_date: "2026-08-23"
updated_at: "2026-07-23T07:34:17.256Z"
---

# Outcome

Domain/application core của Conversation Runtime tiếp nhận message theo contract
typed, idempotent và subject/capability-scoped thông qua persistence port; worker
lifecycle dùng OCC/fencing mà chưa gọi AI Platform thật. Public controller vẫn
fail closed cho tới khi persistence ở VFBIZ-0018 và contract ở VFBIZ-0019 được
tích hợp.

## Constraints

- Chỉ `public_customer` và `authenticated_customer`; chưa mở employee profile.
- Không gọi model, RAG hoặc tool thật. Dùng disabled/fake AI dispatch port.
- Lane này định nghĩa domain/application contract; chưa sửa Prisma model hoặc
  migration. Persistence thuộc VFBIZ-0018.
- Hidden reasoning, raw token, prompt và tool payload không nằm trong public
  event hoặc API PostgreSQL.
- Handoff tồn tại độc lập với WebSocket; disconnect không làm mất queue state.

## Done when

- Typed command/result/error bao phủ message accept, turn claim/complete,
  cancellation và public event cursor.
- Application port yêu cầu client message ID/idempotency, expected conversation
  version, monotonic sequence và fencing token.
- Domain policy loại stale fencing result, invalid transition, oversized input
  và budget reservation không hợp lệ trước khi gọi AI dispatch port.
- Cancellation/timeout/offline handoff được biểu diễn bằng typed transition,
  không phụ thuộc WebSocket.
- Unit/architecture tests chứng minh replay, OCC, fencing, budget và
  customer-safe event invariant; integration/E2E persistence thuộc VFBIZ-0018.

## Checkpoint

- Domain/application core đã hoàn tất sau một vòng review/fix. Exact next action:
  thực hiện các Account/Vehicle hardening prerequisite; chỉ mở VFBIZ-0018 sau
  khi VFBIZ-0032 hoàn tất.

## Evidence

- [x] `npm run verify:api` — 18 suites/66 unit tests, 6 suites/23 E2E,
  lint/typecheck/Prisma/build đạt ngày 2026-07-23.
- [x] `npm run governance:check` — 45 provider-neutral scenarios, docs/work/
  adapter checks đạt ngày 2026-07-23.
- [x] Focused Conversation Runtime — 2 suites/20 tests, scoped lint/typecheck
  và `git diff --check` đạt; reviewer finding P1/P2 đã được sửa một vòng.

### review — 2026-07-23T07:34:16.635Z

Read-only review completed; one bounded fix cycle resolved subject/capability scope, FIFO, lease/date and citation findings with 20 focused tests.

### done — 2026-07-23T07:34:17.256Z

Domain/application core accepted. Persistence remains disabled and is gated by VFBIZ-0032 then VFBIZ-0018.

### post-completion regression note — 2026-07-27

Found while investigating VFBIZ-0127 (postgres-spec tests never wired into
CI, so this went undetected): `ConversationRuntimeRepository`'s abstract
interface (`getSnapshot`, `findAcceptedMessage`, `getTurnExecutionContext`,
`listPublicEvents`, `commit`) had no explicit `now: Date` parameter, so the
concrete Prisma adapter (VFBIZ-0018) fell back to the real wall clock for
session-readability checks instead of the caller's injected
`ConversationRuntimeClock`. Fixed by adding `now`/`ConversationRuntimeCommit.now`
to the abstract interface and threading `this.clock.now()` through every
call site in `ConversationRuntimeService`,
`ConversationTurnDispatcher` and `ExecuteConversationTurnService` (the
latter two gained a new constructor dependency, already resolvable from the
existing `ConversationRuntimeClock` provider in
`engagement-runtime.module.ts`). No behavior change for production (which
always used the real clock anyway); the actual bug this exposed was a
fixed-date integration test fixture silently failing once real time passed
the hardcoded date — a genuine "time bomb," not flakiness. Re-verified:
`npm test` (263), `npm run test:e2e` (63), all 30 `*.postgres-spec.ts`
tests against real Postgres, lint, typecheck, `prisma:validate`,
`test:migrations` — all pass as of 2026-07-27.
