---
id: VFBIZ-0215
title: Enforce API-owned live control for authenticated staging Chat
status: blocked
mode: controlled
priority: P0
owner_team: customer-engagement
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
  - root
allowed_paths:
  - backend/api/src/modules/engagement/application/ports/staging-chat-live-control.ts
  - backend/api/src/modules/engagement/infrastructure/cache/redis-staging-chat-live-control.ts
  - backend/api/src/modules/engagement/infrastructure/cache/redis-staging-chat-live-control.spec.ts
  - backend/api/src/modules/engagement/presentation/guards/staging-chat-live-control.guard.ts
  - backend/api/src/modules/engagement/presentation/guards/staging-chat-live-control.guard.spec.ts
  - backend/api/src/modules/engagement/engagement.module.ts
  - backend/api/src/modules/engagement/presentation/conversation.controller.ts
  - backend/api/src/platform/config/env.schema.ts
  - backend/api/src/platform/config/env.schema.internal-ai.spec.ts
  - backend/api/test/e2e/engagement
  - docs/work/items/VFBIZ-0215.md
  - WORK.md
depends_on: []
controlled_signals:
  - authentication
  - pii
  - ai-provider
  - public-contract
exclusive_resources:
  - api-chat-composition
required_checks:
  - npm run verify:api
  - npm run contracts:lint
  - npm run governance:check
revision: 6
review_date: "2026-08-31"
updated_at: "2026-08-02T10:42:45+07:00"
---

# Outcome

Require every authenticated staging Chat request to pass a content-free,
API-owned Redis live-control check after customer authentication and before any
conversation or AI dispatch work.

## Constraints

- Customer issuer, audience, authorized party, subject and scope remain owned by
  the existing API authentication boundary; no AI artifact or activation packet
  becomes customer or dispatch authority.
- The live-control store contains only an opaque control identity digest,
  generation, authority digest, bounded validity window and enabled state. It
  never contains tokens, customer identifiers, prompts, answers or documents.
- Redis is checked on every request. Missing, malformed, expired, pre-issued,
  disabled, rotated or unavailable state fails closed with one sanitized 503.
- There is no in-process cache or local filesystem fallback.
- `disabled` remains the default. `public-release`, anonymous, workforce and
  public-capability Chat remain unavailable.
- Preserve the existing dirty VFBIZ-0211 changes; do not reset or rewrite
  unrelated engagement behavior.

## Done when

- The Redis adapter validates an exact immutable expectation and half-open
  `not_before <= now < expires_at` window from one atomic Redis snapshot.
- The presentation guard performs a fresh check per request and exposes no
  internal control reason or Redis error to clients.
- Disable and generation/digest rotation take effect on the immediately next
  request; Redis outage, malformed state and trusted-clock rollback fail closed.
- The live-control guard executes after `AuthenticatedStagingChatGuard` on all
  Chat session routes.
- Focused unit/E2E security tests and all required checks pass.
- Independent correctness and risk reviewers provide recommendation-only
  findings for the exact delta.

## Checkpoint

- Second-cycle controlled implementation claim
  `claim-df75e17c-35ee-4d6e-b5b1-153a19b00504` and exclusive lease
  `lease-1842861b-d8cf-4a31-b163-765f484f0294` were released after the exact
  release-binding candidate and its evidence were produced.
- The candidate additionally binds every enabled Redis snapshot to the active
  PostgreSQL assistant-release envelope SHA-256 and pointer revision. Missing,
  mismatched or unavailable release projection fails closed; the guard emits
  only bounded content-free closure reasons.
- The candidate does not close
  `VFBIZ-0215:RISK:REDIS-ENABLED-REPLAY:v1`. A previously enabled Redis hash
  can still be replayed while the mutable PostgreSQL release projection remains
  active and matches the static deployment expectation. The projection is not
  an append-only or monotonic disable authority.
- Correctness and risk reviewers both placed exact delta fingerprint
  `af30e0e4412b124ea5f11bb7cf1a931f10e83a06c795da3e614a92594900894a`
  on hold. This was the second review/fix cycle for the same P1 cause, so no
  third implicit patch is permitted.
- New P2 `VFBIZ-0215:RISK:RELEASE-CHECK-STALE-NOW:v1` remains open: release
  resolution uses a time captured before the awaited database query, so the
  release can expire before the request is admitted. Fresh post-query time or
  a database-time/fenced resolution contract is required.
- `VFBIZ-0215:RISK:AUTH-NEGATIVE-EVIDENCE:v1` is closed for guard ordering:
  missing-principal, workforce and public-capability requests are rejected
  before live-control lookup. Real OIDC/AppModule browser evidence remains a
  staging acceptance concern.
- `VFBIZ-0215:RISK:CLOSED-CAUSE-OBSERVABILITY:v1` is closed: logs contain only
  bounded `control` and `reason` values and the client receives a sanitized
  503. Warning-volume control remains an operational follow-up.
- Exact decision required from the accountable architect and security owner:
  choose either an append-only PostgreSQL disable ledger with fenced transition
  and rollback semantics, or explicitly accept Redis restore/write authority
  as re-enable authority. Until then, authenticated staging dispatch and public
  Chat remain disabled.

### Second-cycle evidence — 2026-08-02

- [x] Focused live-control/config tests — 72 passed; focused assembled E2E —
  21 passed.
- [x] `npm run verify:api` — lint, type-check, 455 unit tests, 76 E2E tests,
  Prisma validation and build passed.
- [x] `npm run contracts:lint` — passed.
- [x] `npm run governance:check` — passed.
- [x] Independent correctness review — no P0; P1 replay remains open and one
  public-capability fixture limitation recorded.
- [x] Independent risk review — HOLD; no P0, replay P1 remains open, release
  freshness P2 opened, prior authorization/observability P2 findings closed.
- [ ] Acceptance — blocked on the monotonic kill-switch authority and release
  freshness decisions; no agent accepted risk or release authority.

### First-cycle checkpoint

- Controlled implementation claim
  `claim-bce7561b-f9ae-4dc4-9c9a-05c04ea12873` was released with focused
  evidence after the Customer Engagement integration completed.
- `EngagementModule` now composes the exact Redis expectation and
  `ConversationController` applies `AuthenticatedStagingChatGuard` before
  `StagingChatLiveControlGuard` on all eight routes.
- API Foundation delivered the five-field environment contract through
  coordination `coord-262060e8-6916-4599-a09d-c5aace0ab951`; missing, partial,
  malformed or stray values fail environment validation.
- The Redis adapter performs one exact `HGETALL` per request, rejects backward
  trusted-clock movement and fails closed on missing, malformed, disabled,
  rotated, expired or unavailable state. Client responses remain sanitized.
- Correctness review accepted exact delta fingerprint
  `7ca83ccd119240bb7d11be04dd4cee8bb232379c746e0b1c82df8c6581377d06`
  with no P0-P3 findings.
- Independent risk review holds acceptance on
  `VFBIZ-0215:RISK:REDIS-ENABLED-REPLAY:v1`: restoring the prior enabled hash
  with the same immutable expectation can reopen Chat inside the validity
  window. Solving this requires an authority decision or a monotonic control
  revision anchored outside the replayable hash; an in-process latch would
  violate this work item's stateless constraint.
- Two P2 evidence gaps remain recorded:
  `VFBIZ-0215:RISK:AUTH-NEGATIVE-EVIDENCE:v1` and
  `VFBIZ-0215:RISK:CLOSED-CAUSE-OBSERVABILITY:v1`.
- Exact next action: define the external monotonic kill-switch authority and
  bounded content-free operational telemetry, then run one controlled fix and
  independent risk re-review. Public Chat and staging dispatch remain disabled.

## Evidence

- [x] Focused live-control/config tests — 57 passed; assembled engagement E2E —
  18 passed.
- [x] `npm run verify:api` — lint, type-check, 440 unit tests, 73 E2E tests,
  Prisma validation and build passed on 2026-08-02.
- [x] Independent correctness review — two P0 runtime/config bypasses and two
  P1 clock/integration-evidence findings were closed; exact delta accepted with
  no P0-P3 findings.
- [x] `npm run contracts:lint` — passed.
- [x] `npm run governance:check` — passed.
- [x] Independent risk review — no P0; one P1 replay-authority hold and two P2
  evidence/observability findings recorded. Risk was not accepted.

### ready — 2026-08-01T09:07:38.098Z

Coordination-safe API-owned live-control contract is decision-ready; public Chat remains disabled.

### active — 2026-08-01T09:07:38.246Z

Begin clean-path implementation under Customer Engagement ownership.
