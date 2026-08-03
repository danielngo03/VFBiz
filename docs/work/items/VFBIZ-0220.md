---
id: VFBIZ-0220
title: Establish signed remote authority broker for controlled GCP apply
status: active
mode: controlled
priority: P0
owner_team: agent-platform
accountable_role: release-owner
primary_workspace: root
affected_workspaces:
  - root
  - infra
  - api
allowed_paths:
  - contracts/governance/gcp-controlled-apply-authority.schema.json
  - contracts/governance/gcp-controlled-apply-authority.vectors.json
  - contracts/governance/gcp-controlled-apply-verified-envelope.schema.json
  - contracts/governance/gcp-controlled-apply-verified-envelope.vectors.json
  - tools/check-runtime-contracts.mjs
  - tools/gcp-controlled-apply.mjs
  - tools/lib/gcp-controlled-apply.mjs
  - tools/lib/gcp-authority-broker.mjs
  - tools/lib/gcp-signed-authority.mjs
  - tests/governance/gcp-authority-broker.test.mjs
  - tests/governance/gcp-controlled-apply.test.mjs
  - tests/governance/gcp-signed-authority.test.mjs
  - infra/gcp/controlled_apply_broker.tf
  - infra/gcp/variables.tf
  - infra/gcp/outputs.tf
  - infra/gcp/tests/controlled_apply_broker.tftest.hcl
  - infra/gcp/README.md
  - backend/api/src/modules/access
  - backend/api/prisma
  - docs/work/items/VFBIZ-0220.md
  - docs/work/plans/vivi-gcp-ai-platform.md
  - docs/INDEX.md
  - docs/INDEX.json
  - WORK.md
depends_on:
  - VFBIZ-0218
  - VFBIZ-0219
controlled_signals:
  - authentication
  - authorization
  - cloud-infrastructure
  - credential
  - iam
  - migration
  - public-contract
exclusive_resources:
  - agent-control-state
  - api-migrations
  - gcp-vinfast-development
  - public-contract
  - terraform-state
required_checks:
  - npm run contracts:lint
  - npm run verify:agent-runtime
  - npm run verify:api
  - tofu -chdir=infra/gcp validate
  - tofu -chdir=infra/gcp test -filter=tests/controlled_apply_broker.tftest.hcl
  - npm run governance:check
revision: 33
review_date: "2026-08-31"
updated_at: "2026-08-02T22:48:00+07:00"
---

# Outcome

Replace local self-asserted execution authority with a private, signed and
separation-of-duties broker protocol. A verified workforce Release Owner may
decide on one exact plan, but only an isolated broker/executor identity can
verify the signed envelope and dispatch the bounded apply job.

## Constraints

- VFBIZ-0218 remains validation-only. No local command, user ADC token or local
  agent-state JSON may authorize or perform an apply.
- The authority envelope uses a versioned canonical projection and an
  allowlisted asymmetric Cloud KMS key version. Hash/generation without a valid
  signature and issuer identity is insufficient.
- Issuer, broker and executor service accounts are distinct. The human approver
  cannot impersonate the executor; the issuer cannot apply; the executor cannot
  issue or alter decisions.
- Workforce approval binds the verified subject, `release-owner` capability,
  work item/action, full Git revision, plan path/SHA-256, plan semantic digest,
  claim/fencing/lease snapshot digest, exact project/resources, expiry and one
  nonce. Requester and approver must differ.
- Broker state and replay ledger live in an authoritative transactional store;
  local agent-control state is advisory input only. One nonce can reach at most
  one terminal dispatch receipt.
- Decision and recovery JSON are capped at 64 KiB before parsing. Unknown keys,
  duplicate JSON keys, non-canonical payloads, stale KMS versions, expired
  packets and unknown recovery outcomes fail closed.
- The executor consumes an immutable plan snapshot from an exact GCS generation
  and a digest-pinned image. It receives only the minimum service-account
  permissions needed for the reviewed resource set.
- Direct user mutation, executor impersonation and arbitrary-job dispatch must
  be denied by IAM and proven through negative tests and audit evidence.
- Broker/service resources default off. This work item authorizes code, contract,
  tests and no-change planning only; it does not authorize deploy, apply,
  credential mutation, public Chat or release activation.

## Done when

- Contract and independent semantic verifier prove the exact signed envelope,
  canonical digest, KMS key version, issuer/approver separation and payload cap.
- Transactional broker tests cover duplicate/reordered delivery, stale fencing,
  nonce replay, crash/resume, cancellation and terminal receipt immutability.
- IaC tests prove issuer, broker and executor IAM are disjoint, user direct apply
  and TokenCreator paths are absent, services are private and disabled by
  default, and kill switch does not delete evidence.
- The executor accepts only the VFBIZ-0218 semantic plan allowlist, revalidates
  the exact object generation/digest and never accepts arbitrary arguments.
- Negative tests prove operator-self-minted GCS objects, forged local state,
  unsigned recovery receipts, over-size payloads and direct IAM paths fail.
- Default-off saved plan has zero mutation. Any enabled plan/deploy, live deny
  test or credential operation remains a separately recorded named-human gate.
- Independent correctness and risk reviewers recommend the bounded candidate;
  they do not approve deployment or accept risk.

## Checkpoint

- VFBIZ-0218 commit `fb1218b` validates exact plan semantics and disables every
  local execute path with `EXECUTE_BROKER_REQUIRED`.
- VFBIZ-0219 commit `104b1df` closes SQL permission drift; reviewed plan
  `65eedad23f8e5a99cdb8a8634b1f0bf1852e4e97359ea6a25090377c04d7dae7`
  is default-off with 53 resource and 26 output no-ops.
- Final risk review retains four external gaps: unproven authority issuer,
  direct-tofu IAM bypass, non-authoritative local evidence and missing live
  exact-condition canary. It also routes the 64 KiB payload cap here.
- Commit `fd0756c` adds the versioned signed authority/recovery envelope
  contract, canonical vectors and an independent semantic verifier. The
  verifier binds the exact project, plan object generation and digest,
  digest-pinned executor image, KMS key version, issuer identity, requester /
  approver separation, expiry, nonce, role and retry semantics.
- Commit `08bea02` wires an ephemeral P-256 positive/negative crypto self-test
  into the existing contract gate without changing the already-dirty root
  package manifest. Focused signed-authority tests are 8/8 green;
  `contracts:lint`, `verify:agent-runtime` and `governance:check` are green.
- A valid single authority envelope remains deliberately inert:
  `dispatchEligible` is always false. No broker state, GCP resource, credential,
  apply, deployment or public Chat state was created or changed.
- Commit `f27bd4a` closes the first review's numeric schema drift and
  P-256/KMS trust-binding findings. The verifier now pins KMS resource shape,
  enabled state, algorithm and SPKI digest, signs a domain-separated projection,
  rejects RSA/P-384 and returns no aggregate-authority field. Focused tests are
  12/12 green and the risk reviewer recommends proceeding to broker work.
- The second and final correctness review found
  `VFBIZ0220-RUNTIME-SCHEMA-REGEXP-COERCION`: JavaScript `RegExp.test` still
  coerces one-element arrays for `base_revision`, `decision_id`, `plan_uri` and
  `executor_image`, so schema-invalid signed envelopes can be semantically
  accepted. `dispatchEligible` remains false, therefore the defect is inert.
- The two-cycle review/fix budget is exhausted. The affected VFBIZ-0220 lane is
  stopped as a bounded failure and must not be marked acceptance-complete or
  used by a broker until a separately authorized correction requires explicit
  string types for every regex-backed field and supplies parity negatives.
- The project owner separately re-authorized continuation. Commit `e7dd637`
  closes `VFBIZ0220-RUNTIME-SCHEMA-REGEXP-COERCION`: every regex-backed value
  now requires an actual string, unit tests cover array/object attacks and the
  contract gate re-signs schema-invalid candidates before proving both AJV and
  runtime reject them.
- Independent correctness reproduced 44 adversarial signed scalar mutations;
  schema and runtime accepted zero. Independent risk review found no new
  repository issue. Focused tests are 14/14 green; `contracts:lint`,
  `verify:agent-runtime` and `governance:check` remain green.
- The signed-envelope verifier is now a reviewed, non-dispatching input only.
  Exact next action: implement the broker-owned transactional replay/fencing
  model with in-memory conformance tests before choosing a durable store or
  writing any default-off cloud IaC.
- Commit `6ff8625` adds an explicit in-memory conformance model. The first
  review rejected it for queued-expiry TOCTOU, exposed store mutation, stale
  pair/trust readiness, unauthenticated cancellation, missing atomic consume
  mechanics and unbounded clone cost.
- Commit `6c00f32` removes `aggregateReady`, hides the transaction capability,
  refreshes KMS trust and time inside each serialized transaction, rechecks
  both before reservation, caps pair capacity and models reserve/complete/
  cancel only as synthetic conformance. There is no dispatch method; every
  view hard-codes `dispatchEligible=false`.
- The second correctness and risk reviews found no residual P0/P1 inside this
  deliberately synthetic, single-process scope. Focused authority/broker tests
  are 27/27 green and the complete governance suite passes. A P2 remains:
  real `human-issued` envelopes must be hard-rejected or architecture-blocked
  before this model can be called acceptance-complete.
- Durable multi-process PostgreSQL ownership, workforce approval/cancellation
  evidence and the internal facade are now blocked on API Foundation response
  to coordination `coord-49f4b10e-4536-4a27-b826-88f3ae2bf077`. This does not
  block other independent non-release lanes and grants no cloud authority.
- Commit `87cc11a` implements the final risk review's P2 recommendation. The
  conformance model now hard-rejects `human-issued` envelopes and architecture
  tests forbid both controlled-apply runtime entrypoints from importing it.
  Authority/broker tests are 29/29 green and `contracts:lint` passes. This
  post-review hardening narrows the model further; it does not replace the open
  API Foundation coordination or create a production broker.
- API Foundation has responded to coordination
  `coord-49f4b10e-4536-4a27-b826-88f3ae2bf077` with a read-only architecture
  recommendation: agent-platform owns the protocol/verifier/conformance layer;
  API Foundation owns a future durable aggregate, Prisma migration,
  transactional repository and exported internal facade inside the existing
  access context. No new top-level module or public HTTP route is appropriate.
- The coordination remains unclosed until the normalized verified-envelope
  projection and authenticated workforce approval/cancellation evidence
  boundary are sealed and the privileged capability reuse decision is
  explicit. Only then may an `api-migrations` lease and API writer lane begin.
- Commit `7aa49aa` introduced the first normalized projection candidate. Three
  independent reviewers rejected it because a detached document could be
  self-attested by recomputing SHA-256, its runtime shape checks were weaker
  than the schema and signed human fields had authority-confusing names.
- The current correction removes detached acceptance: a consumer must supply
  the original canonical signed envelope so the verifier rechecks signature,
  trust root, expiry and semantics and then requires byte-equivalent normalized
  output. The deployment verifier revision is independently pinned, all human
  fields are explicitly `claimed_*` or `signed_payload_*`, and aggregate /
  dispatch flags remain false.
- The signed contract now carries content-free join keys for the future API
  transaction: claim ID/fencing/expiry, issuer/tenant subject-hash binding,
  required capability and policy revision, and immutable approval-event ID /
  revision/schema/time. These remain signed claims only; API Foundation must
  independently look them up and atomically recheck cancellation/replay before
  creating a separate reservation receipt.
- Focused authority/broker tests are 36/36 green. `contracts:lint`,
  `verify:agent-runtime` and `governance:check` are green. No Prisma, migration,
  cloud, credential, deployment, apply or public Chat state changed.
  Exact next action: independent correctness and risk review of this corrected
  boundary; do not acquire `api-migrations` or write durable runtime code until
  both find no P0/P1.
- The final review of commit `6837bfe` closed the earlier detached/full-resign
  findings but found two P1s: coercive parsing of claim/approval timestamps and
  a verification-time TOCTOU caused by embedding observation time in the
  deterministic projection. API consumability also required an immutable
  source-envelope locator before cross-service integration.
- Commit `c89efb6` closes those findings with one canonical RFC3339 UTC parser
  for all four signed timestamps, removes observation time from projection
  equivalence, proves re-verification at a later current time, and binds the
  source envelope SHA-256 plus GCS generation in an immutable locator. Ambiguous
  subject/capability/decision fields are now explicitly claimed/signed-payload
  fields. The capability claim reuses the existing privileged
  `authorization.approval.approve` policy; it still requires an independent API
  entitlement decision, recent MFA and exact approval-event lookup.
- Focused authority/broker tests are 37/37 green and `contracts:lint` is green.
  The two-cycle review/fix budget is now exhausted. This deterministic
  correction is checkpointed but not independently accepted; therefore the
  `api-migrations` lease, durable broker, IAM and cloud lanes remain closed.
  Exact next action: a separately authorized narrow acceptance review of
  `c89efb6` using the recorded timestamp/TOCTOU/source-locator probes; only a
  no-P0/P1 result may reopen durable API implementation.
- The re-authorized narrow acceptance review found and closed timestamp-schema
  and clock-configuration gaps. Commit `da4b506` adds one strict canonical UTC
  timestamp profile to both schemas and the verifier, registers the same
  calendar-valid format in the contract gate, rejects invalid calendar/clock /
  leap-second values, and makes explicit null/NaN/infinite time or window
  configuration fail closed. The positive vectors include a `.123Z` case.
- Cycle-2 correctness, risk and API reviewers then found no P0/P1/P2 in this
  bounded verifier boundary. Observed evidence: 38/38 authority/broker tests,
  contracts lint, governance check and agent-runtime verification are green.
  The normalized boundary is acceptance-complete as an inert input, not as
  authorization: source URI generation remains syntax-only until API fetches
  exact GCS metadata and rehashes bytes; human issuer/capability claims still
  require API-owned workforce/MFA/approval/cancellation joins.
- The API migration gate is now reopened only for a separate implementation
  lane. Exact next action: acquire the `api-migrations` lease and implement an
  API-owned serializable reservation aggregate plus internal verifier facade;
  projection-only input, claimed capability fields and pairing digests remain
  insufficient for reservation.
- Commit `2cd24c6` implements that API-owned boundary in the existing `access`
  context: a durable Prisma reservation ledger, serializable idempotency/nonce
  replay handling, claim/fencing checks, immutable completion/cancellation
  receipts, source digest/generation locator checks, and an internal facade
  with no public route or cloud behavior. Prisma validation/generation, API
  typecheck/lint, focused facade tests (3/3), the migration suite (clean replay,
  schema drift and legacy backfill) and 42 PostgreSQL integration tests pass.
  The reservation receipt is API-derived from the idempotency hash and nonce;
  callers cannot supply an arbitrary receipt.
- This implementation is code-complete but not yet acceptance-complete: an
  independent API/risk review must verify the transaction and terminal-state
  invariants before any IAM/IaC or broker lane can reopen.
- The first API review found a P1: cancellation `eventId` and `eventRevision`
  were validated but discarded by the durable row. Commit `9df1a65` adds both
  fields through a new immutable migration, persists them in the repository and
  aggregate, and tightens terminal-state checks. The refreshed Prisma,
  typecheck, lint, focused facade tests and clean migration replay remain green.
- The API review also records a remaining boundary: the API currently verifies
  that the signed envelope URI embeds the claimed SHA-256 and GCS generation,
  but does not yet fetch that exact object generation and rehash its bytes. The
  future private verifier adapter must perform that lookup before reservation;
  this lane therefore remains code-complete, not acceptance-complete.
- Commit `d14d52c` closes the unsafe default path while that adapter is absent:
  `ControlledApplyReservationFacade` now requires an API-owned authority
  verifier port, and the production module binds a fail-closed implementation
  that rejects every reservation/cancellation until workforce identity, recent
  MFA, capability, approval-event, cancellation-event and exact GCS
  generation/byte rehash joins are supplied. The same commit validates approval
  event IDs, checks terminal replays against claim/fencing first, retries
  serializable completion/cancellation, and keeps the migration upgrade
  preflight explicit for legacy cancelled rows rather than inventing lineage.
  This is a safety closure, not an authority approval or runtime integration.
- Fresh independent API review of `7c3c409` found no new P0/P1. Observed
  evidence: facade 3/3, Prisma validate/generate, API typecheck/lint,
  migration clean replay/schema-drift/legacy verification plus 42 existing
  PostgreSQL integration tests. A direct fail-closed smoke rejected both
  reserve and cancel with `ControlledApplyReservationAuthorityUnavailableError`.
  The review explicitly keeps exact GCS byte rehash and real workforce/MFA/
  approval/cancellation joins open; the default verifier blocks them rather
  than accepting self-attested claims.
- Revision-19 API repository verification remains green: `verify:api` passes
  lint, typecheck, 458 unit tests, 76 E2E tests, Prisma validation and build.
  This does not reopen the broker lane: the production authority verifier still
  rejects reservation/cancellation until API-owned exact GCS generation
  rehash, workforce identity, recent MFA, capability, approval and cancellation
  joins are implemented and independently reviewed.
- Revision-20 removes `reservationReceiptSha256` from the completion input. The
  aggregate and Prisma repository now recompute the expected receipt from the
  immutable reservation idempotency hash and nonce, and reject a corrupted
  stored receipt. API typecheck, lint and the focused reservation suite (3/3)
  pass. This closes caller-supplied receipt substitution; it does not provide
  the still-missing exact GCS byte rehash or workforce approval joins.
- Revision-21 reruns the complete API gate after that change: 458 unit tests,
  76 E2E tests, Prisma validation, typecheck, lint and Nest build all pass.

- Revision-22 independently reruns the complete API gate after the
  server-derived completion-receipt correction: lint, typecheck, 458 unit
  tests, 76 E2E tests, Prisma validation and Nest build all pass. The run
  retains the fail-closed authority verifier; no exact GCS byte rehash,
  workforce/MFA/capability/approval joins, cloud apply, credential mutation or
  public Chat activation occurred. The API reviewer note that callers could
  supply `reservationReceiptSha256` is superseded by Revision-20 and is no
  longer an open finding.

- Revision-23 closes the independent review fingerprint
  `VFBIZ0220-API-RESERVATION-RECEIPT-001`: replay, completed-terminal replay,
  cancellation and active transitions now all call one shared
  `assertStoredReservationReceipt` check before returning or mutating state.
  A focused corruption regression covers terminal replay; lint, typecheck and
  the focused reservation suite (4/4) pass. This validates the durable-row
  invariant only; exact GCS byte rehash and API-owned workforce/MFA/
  capability/approval/cancellation joins remain absent and therefore
  fail-closed.

- Revision-24 reruns the complete API gate after the shared stored-receipt
  validation: lint, typecheck, 459 unit tests, 76 E2E tests, Prisma
  validation and Nest build all pass. The new corruption regression is
  included; the private verifier remains fail-closed and no cloud/IAM,
  credential or public Chat state changed.

- Revision-25 independent API re-review closes
  `VFBIZ0220-API-RESERVATION-RECEIPT-001`: deterministic stored-receipt
  validation is now present before reserve replay, complete, cancel and both
  aggregate terminal transitions. The reviewer reproduced the focused 4/4
  suite and found no residual receipt-path finding. This closes only the
  receipt-integrity fingerprint; source-object rehash and workforce authority
  joins remain separately fail-closed.

- Revision-26 adds the private exact-source-envelope boundary. A reader must
  pin one requested generation and provide provider-verified generation,
  size/CRC32C metadata plus a byte stream; the API independently rehashes the
  stream, enforces the 64 KiB authority cap and rejects generation, size or
  digest drift. Three focused integrity cases (positive, generation/byte
  mutation and oversize) pass. The boundary is intentionally not bound to the
  production verifier yet, so no broker or cloud authority can be activated by
  this change.
- Revision-26 full API verification passes 462 unit tests, 76 E2E tests,
  Prisma validation, typecheck, lint and Nest build.

- Revision-27 independent source-integrity review closes
  `VFBIZ0220-SOURCE-ENVELOPE-BOUNDARY-001`: URI digest/generation binding,
  positive generation, observed metadata and CRC32C Castagnoli comparison are
  all covered; focused source-integrity tests are 4/4 green. The remaining
  item is integration-only: no concrete GCS reader or authority-join verifier
  is wired, so reservation/cancellation stays fail-closed.

- Revision-28 adds the concrete generation-pinned GCS reader candidate. It
  restricts the bucket/object prefix, uses a fixed storage.googleapis.com
  endpoint with `redirect: error`, validates the ADC token, pins the requested
  generation, and exposes only provider generation/size/CRC32C metadata plus
  a streamed body for the independent API rehash. Token-provider failures now
  map to the authority-unavailable fail-closed error, and an early consumer
  stop cancels the response stream. Focused reader/integrity/reservation tests
  are 13/13 green; the complete API suite is 468/468 with typecheck, lint and
  build green. This remains an inert adapter candidate: it is not bound to the
  production authority verifier, so no reservation, broker, cloud or public
  Chat authority is activated.

- Revision-29 reruns the repository acceptance command `npm run verify:api`:
  lint, typecheck, 468 unit tests, 76 E2E tests, Prisma validation and Nest
  build all pass. The provider-unavailable and Redis-offline messages are
  expected fail-closed test paths; no production provider call, cloud
  mutation, credential change, broker dispatch or public Chat activation
  occurred.

- Revision-30 adds an API-owned authority preflight candidate that independently
  rehashes the exact source envelope and compares the signed claim with the
  read-only workforce/approval join. It intentionally does not implement the
  reservation verifier port and returns no verified request, so a stale
  preflight result cannot cross into the separate nonce-reservation
  transaction. Unexpected source-reader failures normalize to
  `authority-unavailable`; typed digest/metadata mismatches remain conflicts or
  validation failures. Focused preflight tests are 6/6 green, API lint and
  typecheck pass. Production remains bound to
  `FailClosedControlledApplyAuthorityVerifier`; a future durable implementation
  still needs one serializable source/join/nonce transaction before any
  authority can be enabled.

- Revision-31 final gates pass after the preflight hardening: `verify:api`
  reports 474 unit and 76 E2E tests plus Prisma validation, typecheck, lint and
  build; `verify:ai` reports 954 passed and 112 conditional skips with Alembic
  offline generation through `20260802_0025`; `contracts:lint`,
  `governance:check`, `docs:check`, `git diff --check` and OpenTofu validation
  are green. The existing Starlette/httpx compatibility warning remains
  non-failing. No cloud resource, credential, broker dispatch, tuning job or
  public Chat state changed.

- Revision-32 adds an unregistered internal atomic reservation coordinator.
  It verifies the exact source envelope before database work, then requires a
  transaction-scoped workforce/approval join re-read immediately before the
  nonce/idempotency reservation. Revocation/cancellation, missing-join and
  source-reader failure tests prove no reservation write occurs; the focused
  source/preflight/coordinator suite is 10/10, with API lint and typecheck
  green. The coordinator is a candidate port only: no transaction-aware
  workforce store exists, `AccessModule` remains bound to the fail-closed
  verifier, and no authority/cloud/public Chat behavior is enabled.

- Revision-33 reruns the full API gate after the application/infrastructure
  boundary correction: 478 unit tests and 76 E2E tests pass, with Prisma
  validation, lint, typecheck and build green. The application architecture
  test now confirms the coordinator depends only on the source-integrity port;
  no infrastructure deep import remains. No cloud, credential, broker or
  public Chat state changed.

## Evidence

- [x] VFBIZ-0218/0219 final reviewer findings and safe default-off state.
- [x] Signed authority/recovery envelope contract and canonical vectors.
- [x] Synthetic in-memory transactional replay/fencing conformance model.
- [x] Durable API-owned transactional replay/fencing aggregate (`2cd24c6`);
  cancellation lineage hardening is in `9df1a65`; independent acceptance
  review remains open for the private verifier adapter and exact-object fetch
  boundary. `d14d52c` makes the default path fail-closed.
- [ ] Separation-of-duties IAM and direct-path denial tests.
- [ ] Private default-off broker/executor IaC and no-change plan.
- [x] Independent correctness and risk recommendations for the signed-envelope
  verifier; neither recommendation authorizes broker deployment or apply.
- [x] Narrow acceptance review of the normalized boundary; no P0/P1/P2 after
  `da4b506`.
- [x] Fresh API review of `7c3c409`; no new P0/P1, with exact-object and
  authority-join work intentionally blocked by the fail-closed default.
- [ ] Named-human deploy/live-deny/canary decision; not authorized here.
- [x] Revision-19 fresh API verification and fail-closed reservation/cancel
  smoke; no cloud, IAM, credential or public Chat mutation.
- [x] Revision-20 server-derived completion receipt invariant; caller no longer
  supplies a reservation receipt and focused API checks remain green.
- [x] Revision-21 full API verification after the receipt invariant; no cloud,
  IAM, credential or public Chat mutation.
- [x] Revision-22 independent full API verification confirms the same green
  gate and records that the caller-supplied reservation receipt finding is
  closed; authority joins and exact-object rehash remain fail-closed.
- [x] Revision-23 shared stored-receipt validation closes the replay and
  cancellation corruption finding; focused API checks pass and no cloud or
  release authority changed.
- [x] Revision-24 complete API verification after the replay/cancellation
  integrity fix: 459 unit tests and 76 E2E tests pass; no cloud or release
  authority changed.
- [x] Revision-25 independent API re-review closes the stored-receipt
  fingerprint with no residual finding; no cloud, IAM, credentials or public
  Chat state changed.
- [x] Revision-26 exact-source-envelope integrity boundary and focused tests;
  the production verifier remains fail-closed pending workforce/MFA/
  capability/approval/cancellation joins.
- [x] Revision-26 full API gate: 462 unit tests and 76 E2E tests pass with
  Prisma validation and build; no cloud or release authority changed.
- [x] Revision-27 independent review closes the source-envelope integrity
  fingerprint; no concrete provider wiring or cloud/release mutation occurred.
- [x] Revision-28 concrete GCS reader hardening and focused 13/13 tests;
  token failures and early stream termination fail closed, while production
  verifier wiring and workforce authority joins remain explicitly open.
- [x] Revision-29 complete `verify:api` gate: 468 unit tests and 76 E2E tests,
  Prisma validation, typecheck, lint and build; no cloud or release mutation.
- [x] Revision-30 authority preflight candidate: focused 6/6 tests plus API
  lint/typecheck; the candidate is not a verifier implementation and cannot
  cross a reservation transaction, while production remains fail-closed.
- [x] Revision-31 complete repository gates: API 474 unit/76 E2E, AI 954
  passed/112 conditional skips, contracts, governance, docs, diff and OpenTofu
  validation all green; no cloud or release mutation.
- [x] Revision-32 atomic reservation boundary candidate: source verification
  plus transaction-scoped join recheck and no-write failure tests (10/10);
  unregistered and fail-closed pending a real workforce transaction store.
- [x] Revision-33 full API verification after boundary cleanup: 478 unit/76
  E2E, Prisma validation, lint, typecheck and build green; no cloud or release
  mutation.
