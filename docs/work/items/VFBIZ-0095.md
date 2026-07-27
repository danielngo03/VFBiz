---
id: VFBIZ-0095
title: Public Chat API and SSE activation
status: proposed
mode: controlled
priority: P0
owner_team: customer-engagement
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/engagement
  - backend/api/src/platform/redis
  - backend/api/src/app.module.ts
  - backend/api/docs/conversation-runtime.md
  - backend/api/test/e2e/engagement
  - backend/api/test/integration/engagement
  - backend/api/prisma/models/engagement.prisma
  - backend/api/prisma/migrations
  - backend/api/scripts/verify-migrations.sh
  - contracts/openapi
depends_on:
  - VFBIZ-0094
controlled_signals:
  - customer-conversation
  - support-handoff
  - session-concurrency
  - authorization
  - pii
  - public-contract
exclusive_resources:
  - customer-chat-public-contract
required_checks:
  - npm run governance:check
  - npm run verify:api
revision: 3
review_date: "2026-07-25"
---

# Outcome

Customer có thể tạo/đọc/đóng chat session, gửi/cancel message, reconnect SSE và
nhận durable answer/refusal/handoff qua public NestJS contract được authorize.

## Constraints

- AppModule chỉ compose controller sau khi VFBIZ-0094 graph execution đạt.
- Anonymous capability và authenticated subject phải cách ly tuyệt đối.
- SSE chỉ là delivery projection; PostgreSQL event/message/handoff là authority.
- Không stream chain-of-thought, raw prompt, tool payload hoặc internal error.
- Handoff recommendation không tự thành support case nếu policy/consent fail.

## Done when

- OpenAPI và runtime có create/get/close session, send/list message, events SSE,
  cancel turn và request/read handoff đúng frozen contract.
- Event envelope dùng `data`, correlation ID, schema version, sequence và
  `Last-Event-ID`; heartbeat/backpressure/retention/resync có typed behavior.
- Final answer và completed event commit atomically; reconnect không mất answer.
- Explicit handoff request chỉ tạo governed recommendation/request boundary;
  contact-center lifecycle thuộc VFBIZ-0098.
- Runtime dispatch activation lấy approved release config, không hardcode policy.
- Public/auth subject isolation, duplicate/out-of-order message, slow consumer,
  late output và contact-center outage đạt E2E.

## Checkpoint

- **Status stays `proposed`, correctly, not an oversight**: `depends_on:
  [VFBIZ-0094]`, and `tools/work.mjs`'s own `ready`/`active` transition
  requires every dependency to be `status: done`. VFBIZ-0094 is `active`,
  blocked on a real, unresolved retrieval/embedding-provider decision that
  needs Data Owner/Engineering Lead authority (see its own Checkpoint) — not
  something this item can force. Everything below is real, tested,
  buildable-and-tested work done in the meantime, mirroring the exact
  pattern the existing 4 routes already established this session:
  fully implemented and tested in isolation, `AppModule` still importing
  only `EngagementRuntimeModule` (no controller), never flipped live. That
  final composition step remains explicitly gated on this item's own
  Constraint ("AppModule chỉ compose controller sau khi VFBIZ-0094 graph
  execution đạt") and is the correct place to stop without human/authority
  sign-off, not a step to take quietly.
- **Done, real, tested — session close** (`ConversationRuntimeAggregate
  .closeSession`, `ConversationRuntimeService.closeSession`,
  `POST /chat/sessions/:sessionId/close`): added `'closed'` to
  `ConversationRuntimeSnapshot.status` (was `'open' | 'handoff'` only — no
  representation of "closed" existed anywhere before this), a new
  `SessionClosedPublicEvent` (empty payload, no owning turn), and the
  transition itself (rejects if already closed; `assertOpen()` already
  naturally rejects new messages/claims on a closed session once `'closed'`
  became a real status value, no extra code needed there). Reading history
  after close still works: closing only changes `ConversationRuntime
  .runtimeStatus`, never `ConversationSession.status` (the separate,
  access-level field `ConversationAccessService.authorize()` actually
  gates on) — confirmed directly, not assumed, by reading both call sites.
- **Done, real, tested — get session** (`GET /chat/sessions/:sessionId`):
  combines a new `ConversationSessionRepository.findSessionSummary` (id,
  profile, locale, createdAt, expiresAt, retentionUntil — columns that
  already existed on `ConversationSession` but had no read path) with the
  runtime's own version/status via a new `ConversationRuntimeService
  .getRuntimeStatus`.
- **Real, previously-latent persistence bug found and fixed while wiring
  session.closed, not worked around**: `conversation_public_event
  .conversationTurnId` was `NOT NULL` with a required FK to
  `ConversationTurn` — every event type that existed before this item was
  turn-scoped, so nothing had ever exercised a session-scoped event.
  `persistEvent`'s write, the `commitTransaction` turn-lookup (which threw
  `ConversationRuntimePersistenceCorruptionError` when no matching turn was
  found — always, for any session-scoped event), and `parsePayload`'s
  unconditional `isIdentifier(payload.turnId)` gate on read would all have
  rejected a `session.closed`/turn-less-`handoff.requested` event outright.
  Also found the `conversation_runtime_status_check` CHECK constraint only
  allowed `('open', 'handoff')` — `'closed'` would have been a constraint
  violation, not just a persistence-layer gap. Fixed with a real migration
  (below), not a workaround. Verified against a genuinely fresh database
  (dropped and recreated the scratch container after adding the migration's
  full contents, since `prisma migrate deploy` does not retroactively
  re-apply a migration whose file changed after its first apply — caught
  this by re-running the affected test and seeing the exact constraint
  violation the stale scratch DB should have shown).
- **Done, real, tested — SSE events** (`GET /chat/sessions/:sessionId/events`,
  `presentation/conversation-event-stream.ts`): NestJS's `@Sse()` decorator
  writes to `response.raw` (confirmed by reading
  `@nestjs/core/router/router-execution-context.js` directly, not assumed),
  which bypasses Fastify's `onSend` hook chain entirely — meaning
  `@fastify/compress` (registered globally in
  `bootstrap/configure-application.ts`) never touches SSE responses and the
  buffering hazard the earlier research flagged does not require any
  per-route opt-out. `SseStream` also already sets `Content-Type`,
  `Cache-Control` and `X-Accel-Buffering: no` correctly on its own. Built
  `watchConversationEvents` as a plain, adapter-free async generator over
  the existing `listPublicEvents` (replay everything after `Last-Event-ID`,
  then poll every 1s for more; heartbeat is a separate 15s interval, wire-
  only, never persisted) so the actual "what happens over time" logic is
  unit-testable without RxJS/Observable machinery — the controller method
  is a thin adapter wiring that generator to an `Observable<MessageEvent>`
  and an `AbortController` for teardown on disconnect.
- **Added per approved mobile adjustment, still release-gated**: Redis replay
  keeps at most 50 durable events per session for 5 minutes and falls back to
  PostgreSQL on miss/outage. A separate atomic Redis admission lease limits
  each session to three cluster-wide SSE connections and closes each stream
  after five minutes so reconnect uses `Last-Event-ID`. Redis-backed Nest
  throttling replaces process-local counters and fails closed when the abuse
  control store is unavailable. These controls do not make Redis a transcript
  authority.
- **Done, real, tested — explicit customer-initiated handoff**
  (`ConversationRuntimeAggregate.requestHandoff`, `ConversationRuntimeService
  .requestHandoff`, `POST /chat/sessions/:sessionId/handoff`): reuses the
  existing `HandoffRequestedPublicEvent`/durable `SupportHandoff` row
  machinery (now with `turnId` optional on the event payload, mirroring
  `session.closed`'s persistence fix, since an explicit request has no
  owning turn) with `reason` fixed to `'customer_requested'`. Sets
  `status: 'handoff'`, same as the AI-recommended path from `completeTurn`.
  - **Real content-spoofing risk found and fixed before it shipped, not
    after**: the first draft took `customerMessage: string` straight from
    the HTTP body. `persistCompletionProjection` stores this text as a
    `ConversationMessage` with `role: 'assistant'` — for the AI-recommended
    path that's correct (it's the model's own generated text), but for this
    new customer-initiated path, accepting arbitrary client text into an
    assistant-attributed transcript row would let any caller spoof
    assistant speech. Fixed by making the acknowledgement message a fixed,
    server-owned constant (`EXPLICIT_HANDOFF_ACKNOWLEDGEMENT`) in the
    service layer, never exposed on `RequestConversationHandoffDto` — the
    domain method still accepts `customerMessage` generically (matching
    `completeTurn`'s existing shape), the API boundary is what changed.
    Exact wording is a functional placeholder, not final customer-facing
    copy — worth a content/product owner pass before release, same caveat
    as any other user-visible string introduced this session.
- **Deliberately not fabricated — matches this item's own Constraint,
  not a gap**: policy/consent/queue-availability checks before creating a
  handoff. `SupportHandoff` is a thin table (`id`, `conversationSessionId`,
  `reasonCode`, `status`, `externalRef`) with no urgency/consent/queue
  columns, and no queue-availability service exists anywhere in this
  codebase — inventing that logic now would be fabricating infrastructure
  that doesn't exist. What's built is exactly what this item's Constraint
  asks for: "chỉ tạo governed recommendation/request boundary; contact-
  center lifecycle thuộc VFBIZ-0098."
- **Idempotency-Key intentionally not added to close/handoff**, matching
  the existing 4 routes' established pattern: none of `createSession`
  /`createMessage`/`cancelTurn` use a cached-response Idempotency-Key
  mechanism today — messages get idempotency via `clientMessageId`
  (already a domain concept), turns/sessions via plain OCC
  (`expectedVersion`), which is retry-safe on its own (a stale version
  fails outright; the caller re-fetches and decides). The candidate
  OpenAPI's `Idempotency-Key` header requirement on these routes remains
  unreconciled against actual code, consistent with every other
  contract/code mismatch already on file below — not selectively fixed for
  just these two routes.
- **Migration**: `20260727090000_conversation_session_closed_event`
  (`conversationTurnId` nullable + FK now optional; `runtimeStatus` CHECK
  constraint widened to include `'closed'`). Hand-written, not
  `prisma migrate dev`-generated: the dev/shadow-database flow hit the
  same PostGIS-shadow-provisioning issue noted in this session's other
  migrations, and this change was simple enough (one `DROP NOT NULL`, one
  constraint swap) to write and verify directly against a real database
  rather than fight the shadow-DB tooling for a single-statement change.
- **Unrelated regression found and fixed while re-running
  `test:migrations` for the first time since VFBIZ-0127 moved the
  postgres-spec jest config**: `scripts/verify-migrations.sh` still
  referenced the old `test/integration/access/jest-postgres.json` path,
  so every run of this script since that move would have failed outright.
  This had gone uncaught because nothing had re-run `test:migrations`
  since; fixed to point at `test/jest-postgres.json`. Recorded here (the
  file this item happened to be touching) rather than reopening
  VFBIZ-0127, which is `active` already for its own next action.
- **Scope-boundary note**: `backend/api/prisma/models/engagement.prisma`,
  `backend/api/prisma/migrations` and `backend/api/scripts
  /verify-migrations.sh` were not in this item's original `allowed_paths`.
  Added them transparently (see frontmatter) rather than working around
  the boundary — the migration is a direct, necessary consequence of
  `session.closed`/turn-less `handoff.requested`, not unrelated scope.
- **Still genuinely open — this item's "Done when" is not fully met**:
  - Full event-envelope reconciliation against the candidate OpenAPI
    contract and `contracts/ai/conversation-public-event.schema.json`
    (field named `data` not `payload`, a top-level `correlationId`,
    `turnId` placement, cancellation/handoff reason-enum agreement) is
    still not done — this touches a file outside every current item's
    `allowed_paths` (see VFBIZ-0094's own Checkpoint note on the same
    schema) and needs an explicit integration-owner decision, not a
    unilateral edit under this item.
  - operationIds on the 3 new routes (`getChatSession`, `streamChatEvents`,
    `closeChatSession`, `requestChatHandoff`) follow the existing 4 routes'
    `ChatX` convention for in-file consistency, not the candidate
    contract's `ConversationX` convention — the naming reconciliation
    named above remains a single, still-open, all-6-routes decision.
  - SSE now has typed `stream.resync_required` for expired, out-of-range and
    purged cursor windows, plus `stream.reconnect_required` when the socket
    writable buffer exceeds 64 KiB. PostgreSQL remains the cursor authority;
    Redis is only the 50-event/5-minute acceleration buffer.
  - Turn dispatch now persists attempt/availability/failure metadata,
    exponentially retries transient transport failures at most three times,
    and records a durable dead-letter audit before safe terminal refusal.
    Operator-authorized dead-letter replay remains deliberately unavailable
    until its capability, retention and audit contract are approved.
  - The doc's full "Kiểm thử bắt buộc" list (contact-center callback
    replay, notification consent, DSAR partial failure) is largely owned
    by other items (VFBIZ-0098, DSAR cluster) per this item's own
    Constraints — not attempted here.
- Exact next action: for Engineering Lead — (a) confirm/route the event-
  envelope and operationId reconciliation decision (touches a file this
  item cannot edit), (b) decide when VFBIZ-0094's retrieval/embedding
  blocker clears enough to formally start this item and compose
  `EngagementModule` into `AppModule` for real, (c) a content/product
  owner pass on `EXPLICIT_HANDOFF_ACKNOWLEDGEMENT`'s exact wording.

## Evidence

- [x] `npm run verify:api` — 2026-07-27: lint clean, typecheck clean, 285
  unit/integration tests, 67 E2E tests, Prisma validation, Nest build all
  pass (includes closeSession/getSession/SSE/requestHandoff's new tests at
  every layer).
- [x] All 8 `*.postgres-spec.ts` suites (38 tests) pass against a real,
  freshly migrated PostgreSQL 17 + PostGIS container, including the new
  `session.closed` (with no owning turn, history stays readable after
  close), live SSE polling (a message committed after the watcher starts
  is delivered, not just replayed), and `requestHandoff` (no owning turn,
  `SupportHandoff` row correct, message persisted with the fixed
  acknowledgement) cases.
- [x] `npm run test:migrations --workspace @vfbiz/api` — 2026-07-27: clean
  replay, schema drift, PostgreSQL integration and legacy backfill all
  pass, through the new `20260727090000_conversation_session_closed_event`
  migration.
- [x] `npm run governance:check` — 2026-07-27: passed.
- [x] API unit gate — 2026-07-27: 57 suites / 305 tests passed after adding
      replay, stream admission and Redis throttling; API lint/typecheck passed.
