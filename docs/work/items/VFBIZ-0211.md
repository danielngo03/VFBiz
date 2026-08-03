---
id: VFBIZ-0211
title: Add privacy-safe AI observability and authenticated staging Chat
status: active
mode: controlled
priority: P0
owner_team: ai-model-platform
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
  - api
  - customer-portal
  - root
allowed_paths:
  - backend/ai/app/infrastructure/observability
  - backend/ai/app/bootstrap/release_runtime.py
  - backend/ai/app/modules/evaluation
  - backend/ai/app/modules/governance/application
  - backend/ai/app/modules/governance/infrastructure
  - backend/ai/scripts
  - backend/ai/tests
  - backend/ai/pyproject.toml
  - backend/ai/uv.lock
  - backend/api/src/app.module.ts
  - backend/api/src/modules/engagement
  - backend/api/src/platform/config
  - backend/api/test
  - apps/customer-portal/src/app/bff/chat
  - apps/customer-portal/src/app/(account)/chat
  - apps/customer-portal/src/components/layout/site-header.tsx
  - apps/customer-portal/src/features/chat
  - apps/customer-portal/src/platform/api/customer-api.ts
  - apps/customer-portal/src/platform/api/http-responses.ts
  - apps/customer-portal/src/proxy.ts
  - apps/customer-portal/src/styles/globals.css
  - apps/customer-portal/tests
  - contracts/openapi/customer-conversation-candidate-v1.yaml
  - contracts/ai/conversation-public-event.schema.json
  - contracts/ai/assistant/public-event.schema.json
  - tools/check-runtime-contracts.mjs
  - infra/gcp
  - docs/work/items/VFBIZ-0211.md
  - WORK.md
depends_on:
  - VFBIZ-0209
controlled_signals:
  - ai-provider
  - ai-observability
  - authentication
  - public-contract
  - pii
exclusive_resources:
  - ai-provider-registry
  - api-chat-composition
required_checks:
  - npm run verify:ai
  - npm run verify:api
  - npm run verify:apps
  - npm run contracts:lint
  - npm run governance:check
revision: 17
review_date: "2026-08-31"
updated_at: "2026-08-03T02:54:00+07:00"
---

# Outcome

Provide an authenticated staging Chat path that exercises the governed
conversation flow with Vertex candidates and privacy-safe Langfuse
observability, without enabling anonymous or production Chat.

## Constraints

- Product `/api/v1/chat` routes remain unmounted by default. Staging composition
  must require a verified customer subject, exact client and `chat:use` scope;
  workforce, anonymous and public-capability access fail closed.
- Langfuse receives observation metadata, digests, model identity, bounded
  token/cost/latency and outcome only. Raw prompts, answers, retrieved text,
  customer identifiers, documents and vectors are forbidden.
- Langfuse credentials live in GCP Secret Manager. They are never written to
  `.env`, Git, fixtures, logs or operator packets.
- The staging path uses synthetic or development-only evidence and has an
  explicit kill switch. It grants no source, Brand, Legal, Data, Privacy or
  Release approval and cannot materialize an active production retriever.
- No LangChain or LangGraph dependency is added merely for tracing. Existing
  LangGraph remains the conversation orchestration boundary; observability is
  OpenTelemetry-compatible and vendor-adapted at infrastructure.
- Public Chat activation remains owned by VFBIZ-0195 after VFBIZ-0194,
  VFBIZ-0196 and VFBIZ-0197.

## Done when

- A sanitized Langfuse development trace is visible and contains no raw
  content.
- Authenticated staging composition is impossible in production and anonymous,
  workforce and public-capability access have deterministic negative tests.
- Candidate OpenAPI, controller responses and SSE frames have executable
  parity.
- One browser-driven staging flow verifies session, message, refusal/citation
  behavior and kill switch without production corpus.
- Focused security tests and full AI/API/contract/governance gates pass.

## Checkpoint

- Langfuse JP project exists. Secret Manager API is enabled in
  `vinfast-503003`; `vfbiz-langfuse-secret-key-dev` and
  `vfbiz-langfuse-public-key-dev` each contain one version.
- VFBIZ-0209 supplied a successful content-free Vertex generation/embedding
  receipt. It did not authorize product Chat, corpus retrieval or tuning.
- The metadata-only OpenTelemetry adapter emitted two observations into
  Langfuse with input/output content absent. Receipt:
  `a4158487c624ba08b832981808850e0a6265cf72a6c1f8ab5af67179491bdf9d`.
- Local `.env` contains only `GOOGLE_CLOUD_PROJECT`, the pinned JP Langfuse
  origin and two Secret Manager IDs. The emitter resolves both values through
  ADC in memory; the real secret value has zero repository hits.
- The API composition now has a default-off `VFBIZ_CHAT_API_MODE`. Its only
  non-disabled mode is development/test-only, requires internal AI dispatch
  and an authenticated principal, and rejects `public_customer`.
- Focused observability tests pass (`3 passed`); focused Chat gate and endpoint
  tests pass (`13 passed` and `12 passed`). Full `verify:api` passes 383 unit
  and 67 end-to-end tests. Full `verify:ai` passes 704 tests with 95 external
  integration skips; `contracts:lint` and `governance:check` pass.
- Independent risk review permits Secret Manager resource IDs in ignored
  `.env`, not actual credentials. It rejects uploading the existing 100-case
  rehearsal as a managed dataset because its exact manifest says local-only,
  training-forbidden and pending named human decisions.
- The API staging guard and environment mode now use one
  `authenticated-staging` identity. Client-provided `profile` is rejected;
  the controller derives `authenticated_customer` from the verified customer
  principal. E2E object-authorization and throttling tests now exercise an
  authenticated owner plus cross-subject negatives instead of the retired
  anonymous capability-cookie path.
- The 11 lint findings, two stale guard imports and one stale environment test
  were closed. Full API verification passes 387 unit and 67 E2E tests, Prisma
  validation and the production build.
- A content-free authenticated browser-lab activation request now pins exact
  Vertex generation/embedding, fact-free synthetic knowledge, runtime,
  contract, negative-authorization, evaluation and kill-switch digests. It is
  always `human_approved=false`, `training_eligible=false`,
  `release_eligible=false` and cannot represent production retrieval or public
  Chat authority.
- Activation no longer trusts the packet itself. The verifier requires an
  externally pinned packet digest, actual runtime project/environment,
  independently reviewed synthetic evidence and one atomic live
  kill-switch/replay control. It uses an injected trusted clock; exact expiry
  and historical replay fail closed.
- Independent correctness and risk reviews initially found self-attestation,
  stale kill-switch replay, loose client binding, inclusive expiry and a
  caller-controlled clock. All findings were reproduced, fixed and closed in
  final recommendation-only PASS reviews. No reviewer granted human or release
  approval.
- A subsequent cross-boundary architecture review found that browser OIDC is
  already owned by API verification/authorization and the signed internal AI
  assertion. All OIDC/JWT/issuer/audience/scope/subject/principal/token authority
  was removed from the AI lab packet, closing the dual-authority and
  confused-deputy risk. The API trust chain was left untouched.
- Governance/application is the preferred long-term home for this activation
  policy, but the ownership resolver requires separate AI Assurance/Data Owner
  coordination for that path. The current module is unwired and reviewers found
  its temporary placement safe; relocation is tracked rather than bypassing the
  ownership boundary.
- Focused lab/observability verification passes 28 tests. Full `verify:ai`
  passes 785 tests with 100 external/live skips; Ruff, Pyright and migration SQL
  generation are green. Scoped implementation evidence:
  `artifact://vfbiz-0211/authenticated-staging-lab/75a8739572a013dd59b2ed7ae29bd44f02b49d5b53648fb6dee492c72048faac`.
- Exact next action: extend the controlled scope to the Customer Portal and
  implement the browser loopback flow against these concrete adapters and the
  existing API-owned signed internal assertion/live dispatch guard. Do not
  treat lab activation as message-dispatch authority, reuse the local Golden
  rehearsal or activate anonymous Chat.
- Independent VFBIZ-0192 risk review reproduced downstream finding
  `VFBIZ-0192-R14-GOVERNANCE-BINDING-001`: the semantic sealed-evidence gate is
  exercised by tests but the real governance resolver still verifies a generic
  automated-gate artifact. Blocking coordination request
  `coord-6573fa79-6bf9-4879-9b24-4233f96095cd` assigns the authority facade to
  AI Assurance. Staging/public activation remains blocked until the resolver
  binds authority class, recommendation, human-approval flag, run identity and
  bundle digest.
- Revision 8 accepts the coordination-owned technical scope for an Evaluation
  public facade and Governance resolver binding. An isolated implementer lane
  is adding fail-closed checks for exact run/bundle/candidate identity,
  `vinfast-acceptance`, `recommend`, human-approval inclusion and
  `decision_ready`; no evidence or approval is being synthesized.
- Revision 9 wires that facade into the real PostgreSQL release resolver and
  runtime composition. Generic trusted-evidence presence can no longer bypass
  the semantic bundle: the exact `evaluation://<run-id>`, run/bundle/document
  digest, candidate ID/manifest, `decision_ready` state and
  `vinfast-acceptance` authority must all agree.
- Independent review found and closed
  `VFBIZ-0211-SEMANTIC-GATE-UNSAT-001`. Automated Evaluation now requires its
  canonical `needs-human-decision` and `human_approval_included=false`; forged
  `recommend` or human approval is rejected. Governance approvals remain a
  separate mandatory authority and are not replaced by automated evidence.
- A real PostgreSQL seal/read exercise uses
  `PostgresAssistantReleaseEvidenceReader`, observes the immutable canonical
  fields and correctly rejects `public-diagnostic` as release authority. The
  independent closure review reports no remaining scoped P0/P1.
- Revision 10 implements concrete, content-free lab authority adapters:
  deployment-digest-pinned packet/evidence JSON registries, external runtime
  identity, a UTC clock and a private SQLite activation control. Activation is
  one-time under `BEGIN IMMEDIATE`; replay, disabled/mismatched control,
  registry tamper, extra raw-content keys, symlinks, hardlinks and unsafe file
  permissions fail closed. The SQLite control grants no message dispatch,
  customer identity, public or workforce authority.
- Independent review reproduced
  `VFBIZ-0211-LAB-SQLITE-URI-PATH-CONFUSION-001`: an unescaped `?` in a SQLite
  URI could open a different enabled database than the disabled file that was
  validated. Runtime now resolves an existing exact path and opens with
  `uri=False`; the exploit regression closes it. Review also closed
  `VFBIZ-0211-LAB-KILL-SWITCH-UNKNOWN-STATE-001`: disable now returns typed
  `DISABLED`, `ALREADY_DISABLED` or `MISMATCH`, raises on unknown state and
  verifies the disabled post-condition inside and after the transaction.
- The independent re-review reports no remaining P0/P1/P2 in this exact delta.
  It is recommendation-only. Scoped source/test evidence digest is
  `d10b1b31545fb87a369cbba12962273a6579394f62455d664965fc04cff2133a`.
- Revision 11 adds an authenticated `/chat` Customer Portal surface backed only
  by the same-origin BFF. CSRF stays memory-only and the browser never receives
  the OIDC access token. Session creation, message history, bounded SSE,
  cancellation, handoff, explicit close confirmation and citation/refusal
  rendering are implemented; `/chat` is denied to anonymous callers.
- The first independent Portal review found contract drift, stale-cursor loops,
  incomplete mid-turn kill-switch handling and missing destructive confirmation.
  The API controller/repository/DTO projection now matches the authenticated
  candidate contract for session, messages and commands. Durable events are
  mapped from internal `payload/cursor` records into the public typed envelope;
  anonymous capability claims and unsupported server idempotency claims were
  removed instead of being simulated.
- SSE now handles both typed `stream.resync_required` and HTTP 409 cursor expiry
  by clearing the cursor and reloading durable session/messages. Cursor advance
  happens only after a frame is parsed and applied. A 503 observed at stream
  open, message/command dispatch or durable resync locks the UI unavailable.
- Observed checks after remediation: API contract projection `6 passed`; Portal
  unit `11 passed`, component `11 passed`, integration `24 passed`; full
  `verify:api` passes `411` unit and `67` E2E tests plus Prisma/build; full
  `verify:apps`, `contracts:lint` and three browser foundation/anonymous-denial
  tests pass. The credentialed Chat Playwright journey remains correctly
  skipped because the dedicated staging identity/full stack is not available;
  this skip is not acceptance evidence.
- The second and final independent Portal review closed the stale-cursor,
  kill-switch and destructive-action findings. It left one exact contract
  vocabulary finding: internal cancellation/handoff reasons and heartbeat did
  not yet match the public schema. The integration owner then added the missing
  governed reasons, made heartbeat a typed content-free envelope and added
  direct mapper regressions. The review-cycle limit is exhausted, so this is
  observed technical evidence rather than a third review or approval.
- Revision-12 scoped implementation digest before documentation regeneration:
  `b4caa9efbeb52165551a98441d489f83f7c159741fd4fd6dd5df16380a94e537`.
- AI Assurance has formally responded to and closed coordination
  `coord-6573fa79-6bf9-4879-9b24-4233f96095cd`. The implemented Evaluation
  facade and real resolver binding require exact evaluation URI, run, bundle,
  document, candidate and manifest identity plus `decision_ready`,
  `vinfast-acceptance`, canonical `needs-human-decision` and
  `human_approval_included=false`. This closes the coordination ledger only;
  it does not create the unavailable VinFast witness or governance approvals.
- The VFBIZ-0211 overlapping API, Customer Portal and contract paths now have
  a dedicated local checkpoint candidate. Fresh full verification passes 411
  API unit tests, 67 API E2E tests, 11 Portal unit tests, 11 Portal component
  tests, 24 Portal integration tests, both application production builds and
  contract lint. VFBIZ-0215 live-control files remain outside this checkpoint
  for an explicit ownership handoff.
- Fresh `npm run verify:apps` passes both portal workspaces: customer portal
  lint/typecheck, unit 11, component 11, integration 24 and production build;
  workforce portal lint/typecheck, unit 13, integration 6 and production
  build. The credentialed browser journey remains unexecuted because the
  dedicated staging identity/full stack is absent; anonymous denial and local
  contract coverage do not substitute for that runtime evidence.
- Revision-16 full API gate rerun passes lint, typecheck, 458 unit tests, 76
  E2E tests, Prisma validation and the production build (`EXIT=0`). Expected
  provider-unavailable and offline Redis paths remained fail-closed/fallback
  test observations; no provider call or public activation occurred.
- Revision-17 cloud preflight remains release-negative: `vinfast-staging-503003`
  is not accessible to the active operator identity, and the development
  project has no Vertex custom jobs, endpoints or models in the checked region.
  No project was created, no tuning job was submitted and authenticated
  browser staging remains unexecuted pending a dedicated staging identity and
  full private stack.

## Evidence

- [x] Sanitized Langfuse observation
- [x] Secret Manager-backed local configuration without local secret values
- [x] Focused AI/API tests
- [x] Full required checks
- [x] Authenticated-subject E2E access, cross-subject denial and throttle tests
- [x] Externally anchored synthetic browser-lab activation request and verifier
- [x] Independent correctness and risk review of activation authority
- [ ] Browser-driven authenticated loopback Chat and kill-switch evidence
- [x] Customer Portal `/chat`, same-origin BFF, contract projection, SSE
  resync/409, mid-turn kill-switch and anonymous-denial regression coverage
- [x] VFBIZ-0192 semantic evidence coordination responded and closed with the
  authority-correct facade/resolver evidence; `public-diagnostic` and forged
  recommendation/human-approval evidence remain release-negative
- [x] Fresh `verify:api`, `verify:apps` and `contracts:lint` pass before the
  overlapping-path handoff; VFBIZ-0215 live-control files are not silently
  absorbed into this checkpoint
- [x] Revision-16 fresh `verify:api` — 458 unit tests, 76 E2E tests, Prisma
  validation and production build pass; credentialed browser staging remains
  an explicit environment blocker, not a skipped acceptance claim
- [x] Revision-17 read-only GCP/Vertex preflight — staging project access,
  Vertex job/model/endpoint presence and no-provider-call state recorded; no
  cloud mutation performed
- [x] AI Assurance semantic evidence facade integrated into the real resolver;
  focused unit/architecture tests and PostgreSQL seal/reader integration pass
  with independent P1 closure
- [x] Revision-9 full gates — `verify:ai` passes 848 tests with 101 explicit
  external/live skips; `verify:api` passes 405 unit and 67 E2E tests plus
  Prisma/build; contracts, migration SQL, governance and diff checks pass
- [x] Concrete lab adapters and independent remediation review — 33 focused
  packet/runtime tests pass with Ruff and Pyright; path-confusion and unknown
  kill-switch state findings are closed without granting release authority
- [x] Revision-10 AI gate — `verify:ai` passes 867 tests with 101 explicit
  conditional skips; Ruff, Pyright and migration SQL through `0023` pass

### implementation — 2026-08-03

Authenticated customer session creation now reserves a daily subject budget in
the same PostgreSQL transaction as session creation. The new immutable migration
`20260803120000_conversation_subject_budget` prevents session churn from
resetting the AI cost/token cap and maps exhaustion to typed HTTP 429. Prisma
validation, clean/legacy migration replay (42 PostgreSQL tests), API lint,
typecheck and focused service tests pass. Usage reconciliation and credentialed
browser staging remain open follow-up gates.

### implementation — 2026-08-03 (runtime safety follow-up)

Subject reservations are now persisted on the session and reconciled exactly
once when a session closes; expiry cleanup refunds only abandoned sessions,
while privacy erasure does not reset the daily quota. Message creation now
requires an idempotency key bound to `clientMessageId`; Redis replay rejects
gaps, cross-session events and malformed frames before falling back to durable
PostgreSQL replay. The turn lease is derived from provider timeout plus a
margin. Typed conversation errors map to stable problem codes instead of 500.
Fresh API tests (74 suites/481 tests), migration replay (30 migrations, 42
PostgreSQL tests), lint and typecheck pass. Credentialed browser staging and
cloud deployment remain unexecuted because the dedicated staging identity and
zero-destroy apply packet are not present.
