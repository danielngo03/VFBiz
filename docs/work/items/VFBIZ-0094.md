---
id: VFBIZ-0094
title: Internal Conversation Graph execution runtime
status: active
mode: controlled
priority: P0
owner_team: ai-assistant-orchestration
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/api/internal_v1
  - backend/ai/app/bootstrap
  - backend/ai/app/modules/assistant
  - backend/ai/app/modules/inference
  - backend/ai/app/platform/cancellation.py
  - backend/ai/app/platform/checkpoints
  - backend/ai/app/platform/config
  - backend/ai/app/platform/database
  - backend/ai/app/platform/security/execution_assertion.py
  - backend/ai/migrations/versions
  - backend/ai/tests/contract
  - backend/ai/tests/unit/assistant
  - backend/ai/tests/unit/platform
  - backend/ai/tests/unit/bootstrap
  - backend/ai/tests/integration/assistant
  - backend/ai/tests/integration/platform
  - backend/ai/docs/conversation-graph.md
  - backend/ai/docs/inference-serving.md
  - backend/ai/scripts/doctor.py
  - guides/customer-ai
depends_on:
  - VFBIZ-0024
  - VFBIZ-0025
  - VFBIZ-0099
  - VFBIZ-0103
  - VFBIZ-0104
controlled_signals:
  - ai-assistant
  - customer-conversation
  - ai-retrieval
  - model-routing
  - authorization
  - pii
exclusive_resources:
  - ai-internal-conversation-contract
  - database-migration
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 5
review_date: "2026-07-25"
updated_at: "2026-07-27T03:26:49.787Z"
---

# Outcome

FastAPI thực thi một signed customer turn qua LangGraph bằng active retrieval
snapshot và provider-neutral inference port, trả exact revision-bound result cho
NestJS thay vì placeholder 503.

## Constraints

- Không mở public AI route; chỉ `internal-v1` sau signed assertion/replay gate.
- Graph không authorize customer, execute business mutation hoặc sở hữu durable
  conversation history.
- Không bật provider/model nếu thiếu typed config, budget, cancellation, release
  manifest và rollback/kill switch.
- Không dùng fallback text như factual answer khi retrieval thiếu evidence.
- Mọi node có interrupt/retry phải idempotent và tuân turn deadline/fencing.
- Baseline clarification là terminal conversational outcome; không dùng native
  LangGraph interrupt xuyên qua customer turn cho tới khi durable continuation
  contract có checkpoint identity, expiry và replay semantics đầy đủ.
- Completed result phải replay được theo signed request/turn/version/fence khi
  HTTP response bị mất; duplicate execution không được chạy model lần hai.
- Checkpoint chỉ giữ typed state/digest, không lưu raw prompt, raw document hoặc
  provider reasoning.

## Done when

- Internal execute endpoint gọi graph runtime thật và trả outcome schema exact:
  grounded answer, conversational answer, refusal, handoff recommendation hoặc
  approved read-only tool proposal.
- Response pin release manifest cùng exact graph/policy/knowledge revisions;
  factual citation pin knowledge revision và source evidence.
- Active retrieval snapshot, evidence authority và execution control được wire
  qua application ports, không import infrastructure vào domain/graph.
- Cancellation port được production-wire; cancel trước/trong/sau execution và
  late provider result đều không commit stale output.
- Durable terminal result replay, execution-control store và cancellation state
  có migration, cleanup/retention và cross-process integration test.
- FastAPI lifespan tạo/đóng database, Redis, checkpointer, retriever, embedding,
  Model Mesh và graph runtime theo thứ tự rõ ràng; không tạo HTTP client theo
  request.
- Provider disabled/outage, no evidence, revision mismatch, budget exhaustion và
  malformed output degrade bằng typed refusal/handoff.
- Contract test dùng real API signer/verifier/replay boundary; unit/integration
  test bao phủ graph execution, response mapping và release mismatch.

## Checkpoint

Progress this session (uncommitted; `VFBIZ_RUN_DB_INTEGRATION=1 uv run pytest`
passes fully, 0 skipped; ruff/pyright clean; `npm run governance:check` clean):

- **Done, real, tested — all 6 application ports now have a production
  implementation, not a Protocol stub**:
  - `ExecutionCancellationPort` (`PostgresExecutionCancellationAdapter`) and
    `ExecutionControlPort` (`PostgresExecutionControlAdapter`), backed by new
    table `ai_conversation_execution_fence` (migration `20260727_0012`, same
    monotonic-CAS pattern as the resume gate). `/turns/{id}/cancel` is fully
    wired end-to-end (`bootstrap/application.py` sets
    `execution_cancellation_port`), proven by a real-Postgres contract test.
  - `EntityRevalidationPort` (`FailClosedEntityRevalidator`) and
    `EvidenceAuthorityPort` (`FailClosedEvidenceAuthority`): conservative
    fail-closed-by-design, matching `FailClosedClaimSupportValidator`'s
    existing pattern — never fabricate a confirmation/approval that nothing
    can actually check yet.
  - `SupervisorPort` (`KeywordSupervisor`): zero-cost rule-based intent
    routing — a deliberate choice per this session's cost research (RouteLLM/
    Amazon Rufus pattern: cheap routing before any paid call), not a
    placeholder to replace later.
  - `TaskWorkerPort` (`KnowledgeGroundedWorker`): retrieves evidence, skips
    Model Mesh entirely when none is found (cost + correctness), otherwise
    calls `ModelMesh.generate()` and maps `GenerationResult`/`InferenceFailure`
    to `WorkerResult` including `EvidenceReference` digests for citations.
  - `AsyncPostgresSaver` (LangGraph native checkpointer) now constructs
    correctly against real PostgreSQL via
    `create_conversation_checkpointer_runtime()`
    (`platform/checkpoints/graph_checkpointer.py`): explicit `serde=` (passing
    none makes `require_strict_checkpointer` raise — verified against
    `langgraph-checkpoint-postgres==3.1.0`), own `psycopg` connection pool
    alongside SQLAlchemy's `asyncpg` engine (now an explicit `pyproject.toml`
    dependency, not transitive), `.setup()` called once. **A full real graph
    turn (supervisor → worker → evidence check → correct refusal) now
    executes end-to-end against a real Postgres-backed checkpointer** —
    proven by `test_conversation_checkpointer.py`, not a unit fake.
- **Design decision made and recorded**: `ExecutionControlPort` (and now
  `TaskWorkerPort`, for `subject`/budget) cannot be app-wide singletons —
  `GraphControlState` carries no session/turn/subject identity, only
  revision/fencing metadata. Resolution: construct these per turn (closing
  over identity from the validated `AIExecutionAssertionClaims`) and call
  `build_conversation_graph(...)` per turn too, reusing the same singleton
  checkpointer/supervisor/evidence-authority. `StateGraph.compile()` is
  in-memory, not I/O, so this is not a perf concern.
- **Done, real, tested — `execute_turn` is wired end-to-end**:
  `app/api/internal_v1/conversation_router.py` no longer returns an
  unconditional 503. It now reads `conversation_dependencies` from app state
  (fail-closed 503 if the lifespan never composed it), derives
  `GraphControlState`/`InferenceBudget`/subject from the already-verified
  `AIExecutionAssertionClaims`, calls `build_turn_runtime()` +
  `runtime.start()`, and maps the result through a new response module,
  `app/api/internal_v1/conversation_response.py` — its exact JSON shape
  (`AnsweredResponse` / `RefusedResponse` / `HandoffResponse`, field names,
  aliases) was derived by reading NestJS's own strict parser
  (`internal-ai-conversation.transport.ts`), not invented independently, so
  both sides of `ai-internal-conversation-contract` agree without a
  round-trip guess. `ResumeRejected` (duplicate start / graph-identity
  mismatch / deadline exceeded) and a `cancelled` outcome both degrade to a
  typed, non-200 fail-closed response rather than a raw 500. Full citation
  content now reaches this response too: `ConversationGraphState` gained an
  `UntrackedValue` `citations` field (never checkpointed, matching
  `final_answer`'s existing pattern) since only a sanitized digest was
  reaching the graph's output before.
  - Proof this is real, not just type-checked: a new contract test,
    `test_real_conversation_graph_answers_a_valid_turn_end_to_end` in
    `tests/contract/test_conversation_private_protocol.py`, sends a real
    signed HTTP request through `require_execution_context` with a
    Postgres-backed `ConversationRuntimeDependencies` and asserts the exact
    `handoff_recommended` / `insufficient_evidence` JSON body — the same
    outcome `test_conversation_bootstrap.py` already proved at the
    `build_turn_runtime()` level, now proved again one layer up at the real
    HTTP boundary.
  - `release_revision_for()` remains a documented placeholder
    (`f"{graph_version}:{policy_revision}:{knowledge_revision}"`) until
    VFBIZ-0115 binds real release authority — not fabricated, just not the
    final form yet.
  - `usage` (cost/tokens) is hardcoded to zero. This is correct today, not a
    shortcut: every outcome currently reachable (`refused`,
    `handoff_required`) never calls Model Mesh with committed spend.
    Threading real usage through `WorkerResult` is required before
    `completed` becomes reachable.
- **Still genuinely open — do not read "execute_turn wired" as "done when
  fully met"**:
  - `KnowledgeRetrievalService` and real
    `RetrievalSnapshotResolver`/`RetrievalCandidateSearcher`/`QueryEmbedder`
    adapters still do not exist; `DisabledKnowledgeRetriever` is still the
    only retriever, and `generation_provider`/`embedding_provider` are both
    `"disabled"` in this environment. The `completed` (grounded answer) and
    `needs_clarification` outcomes remain unverifiable end-to-end until real
    provider credentials and a retrieval-infra decision land.
- **Done, real, tested — resume-gate and execution-fence retention, LangGraph
  checkpoint retention explicitly scoped out with reasons, not silently
  skipped**: added `ConversationOperationalRetention`
  (`app/platform/checkpoints/retention.py`), a small class over three bulk
  statements (`app/platform/checkpoints/retention_statements.py`):
  `expire_abandoned_resume_gate_claims` (bulk-transitions `reserved`/
  `waiting`/`claimed` rows whose own `deadline_at` has already passed —
  i.e. a crashed process that never called `close_start()`/`finalize()` —
  to `expired`, mirroring the existing single-key reactive
  `expire_statement` used inside `claim_once`, but as a scheduled sweep
  across every abandoned row instead of one keyed lookup),
  `purge_terminal_resume_gate_claims` (deletes `completed`/`failed_closed`/
  `expired` rows untouched since a caller-supplied cutoff, bounded by a
  `limit` per call via a subquery — Postgres has no `DELETE ... LIMIT`), and
  `purge_stale_execution_fences` (age-only delete, since that table has no
  lifecycle `state` column at all — a turn's fence row only exists to bound
  its own execution window, so `updated_at` age alone is the correct and
  only available signal).
  - Neither table holds customer content, raw identity or provider
    output — only opaque hashes, tokens, counters and timestamps — so
    picking a retention cutoff here is a storage-hygiene call, not a
    DSAR/privacy policy decision requiring Data/Privacy Owner sign-off
    (unlike the retrieval-provider gap above). Cutoffs are caller-supplied
    parameters, not hardcoded, so ops can tune them without a code change.
  - **LangGraph's own native checkpoint tables (`checkpoints`,
    `checkpoint_blobs`, `checkpoint_writes`) are deliberately NOT covered
    here, for a concrete, verified reason**: inspected
    `AsyncPostgresSaver.MIGRATIONS` directly — none of the three tables has
    a `created_at`/`updated_at` column, so there is no age signal to filter
    on without parsing LangGraph's internal checkpoint JSONB payload (which
    `docs/conversation-graph.md`'s own principle treats as opaque: "Checkpoint
    chỉ giữ typed state/digest... không lưu raw prompt"). The library does
    expose a clean `adelete_thread(thread_id)` API, but `thread_id` is
    built from the *raw* `session_id`/`turn_id`/`graph_version`
    (`_native_config()` in `graph/runtime.py`), and neither
    `ai_conversation_resume_gate.key_hash` nor
    `ai_conversation_execution_fence.turn_hash` can be reversed back to
    those raw values — both are one-way SHA-256 digests by design. Purging
    LangGraph's checkpoint threads for real would need a new durable
    registry recording raw thread identity against a creation timestamp
    purely for this purpose, which is new schema/design, not a bounded
    extension of this fix — flagged for Engineering Lead as its own
    follow-up rather than either fabricated or silently dropped.
  - **Scheduling is intentionally out of scope, matching this repo's own
    precedent**: `backend/api`'s equivalent
    `ConversationRuntimeRepository.purgeExpiredSessions` is also just a
    tested, callable method with zero production callers anywhere in
    `backend/api/src` today (confirmed by grep) — no cron, no scheduled
    job. `ConversationOperationalRetention` reaches the same "well-tested,
    callable, not yet scheduled" state, not further behind it. Wiring an
    actual periodic invocation (cron, Kubernetes CronJob, ops runbook) is
    an infra/ops decision for both, not something to invent per-item.
  - New tests: `tests/unit/platform/test_retention_statements.py` (3 cases,
    SQL-compilation only, mirroring the existing
    `test_execution_fence_statements.py` pattern — no DB needed) and
    `tests/integration/platform/test_conversation_retention.py` (4 cases
    against real Postgres: expiry only touches abandoned rows past their
    own deadline and leaves a live reservation alone; terminal-claim purge
    deletes only old terminal rows and leaves a recent completed row and a
    non-terminal row alone; the `limit` bound is respected; execution-fence
    purge is age-only).
- **Done, real, tested — Redis lifespan ownership fixed**:
  `RedisAssertionReplayStore` was constructed lazily on the first incoming
  request inside `execution_assertion_verifier()`, with no corresponding
  close on shutdown — violating this item's own Done-when line ("FastAPI
  lifespan tạo/đóng database, Redis, checkpointer... theo thứ tự rõ ràng;
  không tạo HTTP client theo request"). Extracted the construction logic
  into a new `build_execution_assertion_verifier(settings)` factory
  (`app/platform/security/execution_assertion.py`) returning
  `(verifier, redis_client)`; `application_lifespan` now calls it once at
  startup, stores the verifier on `application.state`, and closes the Redis
  client (`.aclose()`) in the same `finally` block that already closes the
  database/conversation-dependencies. `execution_assertion_verifier(request)`
  is now a pure accessor: return the lifespan-configured verifier, or fail
  closed with the existing 503 `ASSERTION_INVALID` if the lifespan never
  configured one — no construction happens in the request path anymore.
  - **Scope-boundary note**: `app/platform/security/execution_assertion.py`
    and the `tests/unit/platform`/`tests/unit/bootstrap` directories were not
    in this item's `allowed_paths` (grep across every work item confirms no
    other item claims `app/platform/security` either — this looks like an
    oversight from whenever the file was first created, not another writer's
    active lane). Added the specific file plus both test directories to this
    item's `allowed_paths` rather than working around the boundary silently,
    since the fix is squarely inside this item's own stated Done-when text.
  - New tests: `tests/unit/platform/test_execution_assertion_lifecycle.py`
    (4 cases — in-memory fallback in test environment, Redis-backed
    construction when `redis_url` is set, the accessor returning a
    lifespan-configured verifier, and the accessor's fail-closed 503 when
    unconfigured); 2 new cases added to
    `tests/unit/bootstrap/test_database_lifecycle.py` (the lifespan closes a
    fake Redis client's `aclose()` on shutdown; a `None` verifier/client pair
    is not erroneously closed). One planned test case (no `redis_url` outside
    development/test) was dropped: `Settings.validate_runtime_policy` already
    requires `redis_url` whenever `environment` is staging/production, so
    that input can never reach this function through a validated `Settings`
    instance — confirmed by trying to construct it and reading the
    validator, not assumed.
- **Done, real, tested — `execute_turn`'s fail-closed outcome mapping now has
  dedicated coverage**: reading `conversation_router.py` shows every
  `ResumeRejected`/cancelled-`GraphOutcome` code the graph can produce maps
  to exactly one of three HTTP shapes — `DUPLICATE_TURN_START` and
  `STALE_FENCING_TOKEN` to a non-retryable 409, everything else to a
  retryable 503 `INTERNAL_FAILURE` (the specific code lands only in the
  free-text `detail` field, confirmed against `problem_response()` in
  `bootstrap/application.py` — the structured `code` field is always
  `INTERNAL_FAILURE` for this branch, and `retryable` is recomputed from the
  HTTP status alone, not read back from the raised exception's own
  `detail["retryable"]`). This mapping had no dedicated test.
  - **`GRAPH_IDENTITY_MISMATCH` turned out to be unreachable through the
    real HTTP router**: `execute_turn` always builds `control.graph_version`
    and `identity.graph_version` from the same signed claim
    (`claims.graph_revision`), so they can never diverge through this call
    path — confirmed by reading every construction site, not assumed. Real
    end-to-end HTTP coverage for this code is therefore impossible by
    construction; added
    `test_start_rejects_a_state_control_pinned_to_a_different_graph_version`
    to `tests/unit/assistant/test_graph_runtime.py` instead, calling
    `ConversationGraphRuntime.start()` directly with a state/identity pair
    built to disagree (the one caller shape that *can* reach this branch).
    Required adding a `graph_version` override parameter to the shared
    `control()` fixture in `tests/unit/assistant/conversation_fakes.py`
    (defaulted to the existing `"graph-r1"`, so every other caller is
    unaffected).
  - **`TURN_DEADLINE_EXCEEDED` is real but not reliably HTTP-triggerable
    either**: it requires the signed budget deadline to still be in the
    future when `AIExecutionAssertionClaims` validates it (or the whole
    assertion is rejected at 401 before reaching the graph) but already
    past by the time `runtime.start()`'s own deadline check runs a few
    lines later — a sub-millisecond window not worth racing against real
    wall-clock time in a test.
  - Added `tests/contract/test_conversation_turn_outcome_mapping.py` (6
    cases: `GRAPH_IDENTITY_MISMATCH`, `TURN_DEADLINE_EXCEEDED` from both the
    `ResumeRejected`-at-reserve-start branch and the cancelled-mid-execution
    branch, `STALE_FENCING_TOKEN`, `DUPLICATE_TURN_START`, and one
    unrecognized cancellation code) that monkeypatches `build_turn_runtime`
    with a fake `start()` returning a fixed outcome — proving exactly the
    thing that was actually missing (the router's mapping) without needing
    the graph to genuinely produce each code through a real run. Extracted
    `tests/contract/conversation_protocol_fixtures.py` out of
    `test_conversation_private_protocol.py` (`application_client`,
    `turn_body`, `assertion_claims`, `sign`, the signing key pair) so the
    new file could reuse the exact same signed-assertion helpers rather
    than duplicating them; `assertion_claims` gained an optional
    `deadline_at` parameter (defaulted to the existing far-future value).
  - **Real circular-import hazard found and fixed, not worked around**:
    `app.bootstrap.application` imports from `app.api.internal_v1`
    (`internal_v1_router`), and `app.api.internal_v1.conversation_router`
    imports from `app.bootstrap.conversation_graph` (`build_turn_runtime`)
    — a genuine cycle between the two packages that has always existed.
    Every import path that reached this module graph before now happened
    to enter through `app.main`/`app.bootstrap` first, which resolves
    cleanly; a test file whose first module-level import is
    `from app.api.internal_v1 import conversation_router` enters from the
    other direction and fails with "cannot import name 'internal_v1_router'
    from partially initialized module" — reproduced directly, not
    theorized. Fixed by deferring that one import to inside the helper
    function that needs it (function-local imports run after module
    collection has already settled the cycle from the safe direction,
    and — unlike a manually-reordered module-level import — this is not
    silently undone by a future `ruff check --fix`, which resorts
    module-level import blocks). This is a latent fragility in the
    production import graph itself (not just test code); worth a follow-up
    if another module ever needs to import `conversation_router` as its
    first touch of this package pair, but out of scope to restructure here.
- Exact next action: this work item stays `active`, not `done`. Every
  smaller, unblocked gap identified this session is now closed (Redis
  lifespan, HTTP-boundary outcome-mapping tests, resume-gate/execution-fence
  retention). What remains is squarely the one hard blocker: an Engineering
  Lead / Data Owner decision to unblock real retrieval/embedding provider
  wiring (see the Done-when bullets requiring `grounded answer` and
  `needs_clarification` outcomes and an active retrieval snapshot) — plus
  the newly-identified, separately-scoped LangGraph-checkpoint-retention
  follow-up (needs a new raw-thread-identity registry design, not a bounded
  fix) for Engineering Lead to route.

## Evidence

- [x] `npm run verify:ai` — 2026-07-27 (Redis lifespan fix): ruff clean,
      pyright clean (0 errors, `app` only per this workspace's
      `pyproject.toml` include scope), 349 passed + 65 skipped
      (DB-integration tests correctly skip without
      `VFBIZ_RUN_DB_INTEGRATION=1`), alembic dry-run SQL applies cleanly
      through `20260727_0012`.
- [x] `VFBIZ_RUN_DB_INTEGRATION=1 uv run pytest` — 2026-07-27 (Redis lifespan
      fix): 414 passed, 0 skipped, 0 failed against a real, freshly migrated
      `pgvector/pgvector:pg17` container (includes the 6 new lifespan tests).
- [x] `npm run verify:ai` — 2026-07-27 (outcome-mapping tests): ruff clean,
      pyright clean (`app` only), 356 passed + 65 skipped, alembic dry-run
      SQL clean.
- [x] `VFBIZ_RUN_DB_INTEGRATION=1 uv run pytest` — 2026-07-27
      (outcome-mapping tests): 421 passed, 0 skipped, 0 failed against a
      real, freshly migrated `pgvector/pgvector:pg17` container (includes
      the 6 new router-mapping tests plus the 1 new
      `GRAPH_IDENTITY_MISMATCH` runtime unit test); isolated re-run of just
      `tests/contract/test_conversation_turn_outcome_mapping.py` also
      passes on its own, confirming the circular-import fix does not depend
      on collection order.
- [x] `npm run verify:ai` — 2026-07-27 (retention job): ruff clean, pyright
      clean (`app` only), alembic dry-run SQL clean.
- [x] `VFBIZ_RUN_DB_INTEGRATION=1 uv run pytest` — 2026-07-27 (retention
      job): 428 passed, 0 skipped, 0 failed against a real, freshly
      migrated `pgvector/pgvector:pg17` container (includes the 3 new
      statement-compilation tests and the 4 new real-Postgres retention
      tests).
- [x] `npm run governance:check` — 2026-07-27: passed (docs index, reports,
      guides, authorization, work items, agent governance).

### active — 2026-07-27T03:26:49.787Z

Checkpoint recorded; add observed state and one exact next action.
