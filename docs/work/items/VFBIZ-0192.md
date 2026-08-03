---
id: VFBIZ-0192
title: Build evaluation execution and evidence authority
status: review
mode: controlled
priority: P0
owner_team: ai-assurance
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai/app/modules/evaluation
  - backend/ai/app/platform/config/settings.py
  - backend/ai/app/platform/database/session.py
  - backend/ai/tests/evaluation
  - backend/ai/tests/integration/evaluation
  - backend/ai/tests/unit/platform/test_settings.py
  - backend/ai/tests/architecture/test_persistence_models.py
  - backend/ai/tests/integration/platform/test_semantic_classifier_binding_persistence.py
  - backend/ai/migrations
  - contracts/ai/evaluation
  - contracts/ai/index.json
  - tools
  - docs/work/items/VFBIZ-0192.md
  - WORK.md
depends_on:
  - VFBIZ-0190
controlled_signals:
  - ai-quality-platform
  - benchmark-runner
  - grader-calibration
  - migration
exclusive_resources:
  - ai-evaluation-contract
  - database-migration
  - evaluation-registry
required_checks:
  - npm run contracts:lint
  - npm run verify:ai
  - npm run verify:ai:integration
revision: 17
review_date: "2026-08-29"
updated_at: "2026-08-03T03:26:00+07:00"
---

# Outcome

Produce reproducible evaluation case results and make a sealed evidence bundle
the only authority that can transition a run to `decision_ready`.

## Constraints

- Evaluation emits evidence and cannot promote a release.
- Public diagnostics cannot become acceptance recommendations.
- Model judge is never the only authority.
- Large traces remain in content-addressed object storage.

## Done when

- Evaluation contracts, Python domain and PostgreSQL mappings have digest parity.
- Released suite loading, sharding, retry, cancellation and budgets are durable.
- Case completeness, calibration and hard gates are proven before sealing.
- An arbitrary digest cannot complete an evaluation run.

## Checkpoint

- Revision-6 independent correctness, domain and risk reviews all rejected the
  candidate. Their P0 findings were canonical Unicode digest divergence and a
  direct-writer path to self-hashed top-level authority claims.
- Revision 7 moves canonical JSON into one shared Python authority and proves a
  Vietnamese plan digest uses it. PostgreSQL now recursively canonicalizes
  JSON with byte-order key sorting, rebuilds the complete expected evidence
  bundle and rejects non-canonical suite, policy, run-result or bundle text.
- Grader calibration now recomputes balanced accuracy and F1 from the confusion
  matrix; a self-consistent digest cannot legitimize false statistics.
- Materialization no longer accepts caller-supplied attempts. It persists
  `attemptPolicy.maxAttempts` from the immutable plan. An expired worker lease
  with unknown provider consumption now reserves every remaining budget,
  records `runner-unavailable` plus `usage-unknown`, and terminates the run;
  it can no longer under-report cost or retry past an uncertain ledger.
- Migration `20260731_0022` continues to refuse unverifiable backfill, binds
  exact leases, accounts every persisted attempt, protects task/run identity,
  recomputes the complete bundle and forbids automated `recommend`.
- Passing automated evidence remains `needs-human-decision`; no Product,
  Brand, Data, Legal, Privacy or Release approval is represented.
- PostgreSQL now owns an immutable released-definition registry for benchmark,
  metric, grader, calibration, suite and baseline policy artifacts. The clean
  infrastructure adapter validates every canonical payload and the runtime
  composition root wires the planner, runner and evidence authority to it.
- Protected metrics require every policy-declared slice, binary observations
  and deterministic Wilson 95% bounds. Python and PostgreSQL recompute the
  same rounded bounds before sealing.
- Runner, sealer and reader are distinct non-login database roles. Capability
  schemas expose only the required operations; none has DML on the underlying
  authority tables. Runtime composition now requires three distinct
  role-specific database URLs and session pools; clean integration tests create
  three real LOGIN members and execute allowed/denied operations as each.
- Revision-8 review found four P1 issues. Revision 9 binds every registry
  column identity to its canonical payload, rejects inserted task attempts that
  differ from the immutable plan, preserves terminal expired-attempt evidence
  when the pinned failure is non-retryable, and uses the exact same Wilson
  constant in Python and PostgreSQL.
- Revision-9 review found two final edge cases: PostgreSQL `NULL` identity
  comparisons and binary-float Wilson arithmetic. Registry identity now uses
  `IS DISTINCT FROM` with missing/JSON-null probes; Python uses 50-digit
  Decimal arithmetic and PostgreSQL-equivalent rounding. An exhaustive
  reviewer probe matched 125,750 Wilson intervals for `n=1..500`.
- Two reviewers approved revision 9, but the independent dataset/evaluation
  reviewer reproduced a remaining run-insert authority bypass plus suite,
  schema, expired-consumption, calibration-slice and numeric-canonical gaps.
  The item is reopened at revision 10; VFBIZ-0211 remains paused.
- Revision 10 now canonicalizes exponent-form numbers identically in
  Python/Node/PostgreSQL, validates every run insert against active released
  benchmark/suite/policy/metric/grader definitions, and re-resolves the exact
  released suite/policy again inside the evidence-seal transaction.
- Released suites now bind authority class, qualification profile, risk
  taxonomy, provenance, contamination scan, held-out status and three
  independent author/evaluator/release-owner subjects. VinFast acceptance
  suites require at least 500 exact case bindings and held-out status in both
  Python and PostgreSQL.
- Calibration slices now carry confusion matrices and recompute balanced
  accuracy/F1; `all` and `high-risk` are mandatory. Benchmark/grader runtime
  documents now validate against their canonical JSON Schemas.
- Revision 11 replaces self-asserted suite metadata with an immutable
  `suite-authority` release record. The record binds the exact case-set digest,
  qualification/profile and risk digests, provenance and contamination
  evidence, held-out status, and distinct dataset-author,
  independent-evaluator and release-owner roles. Suite release, run insertion
  and evidence sealing all require that exact active record.
- Calibration counts are bounded to JCS-safe integers in Python, JSON Schema
  and PostgreSQL. UTC timestamps use one second-resolution `Z` form. Evaluation
  cost uses bounded six-decimal micro-USD precision up to USD 1,000,000 across
  domain, contract semantic validators and database triggers, so an expired
  unknown-usage lease can reserve the exact remaining budget.
- Revision 12 closes the independent parity findings: Node uses the same
  exact-rational derived-metric tolerance as PostgreSQL and compares confusion
  matrices by governed fields rather than object insertion order. Micro-USD
  validation uses exact decimal/exponent scale semantics rather than binary
  multiplication, including exponent-form sub-micro values and the
  `1.000001` binary-float edge. Evaluation duration is capped so the terminal unknown-usage
  result always fits the persisted millisecond column.
- The mandatory `all` calibration slice uses exact equality with the overall
  metrics, while derived matrix-to-metric checks retain the cross-runtime
  `1e-12` tolerance. A sub-tolerance but semantically different `all` metric
  is now rejected by Node, Python and PostgreSQL.
- Two independent revision-12 reviews found no remaining reproducible P0/P1.
  A later runner-role review reopened the item after reproducing a P0 direct
  retry that could replace an expired attempt without first persisting its
  result and usage, plus a P1 terminal-run revival path.
- Revision 13 removes `running -> running` from the database task state
  machine. A retry now requires an exact persisted failed result for the
  current lease and attempt, exactly one plan-bound retryable failure code,
  known usage, cleared lease fields and a remaining attempt. The application
  service uses the same eligibility rule before returning a task to `pending`.
- `cancelled`, `failed` and `invalid` evaluation runs are now immutable in the
  database. A real member of the restricted runner role is regression-tested
  against both direct retry forgery and terminal-run revival.
- The revision-13 re-review confirmed the prior retry and terminal-revival
  reproductions are closed, then found two P1 gaps. Revision 14 serializes
  provider work per run, computes the durable remaining budget before every
  claim and fails the run before dispatch when any plan budget is exhausted.
  Every case lease carries the exact remaining token, duration and cost caps,
  and completion rejects usage above those caps.
- Persistence of `vinfast-acceptance` suite-authority records now fails closed.
  The repository does not have an authenticated external human-witness
  registrar, so a definition writer cannot persist a self-asserted acceptance
  witness. Public-diagnostic authorities remain available for executable
  infrastructure tests.
- Exact next action: accountable technical acceptance must review revision 14
  and decide whether to introduce an authenticated external witness registrar.
  Human Data/Release decisions remain separate and ungranted.
- Revision 15 records a fresh independent reviewer-verifier pass. No P0 or P1
  code defect was reproduced; 45 focused tests, a clean PostgreSQL 17 +
  pgvector replay through migration `0023`, seven definition/run/evidence
  integration tests and contract lint passed. The implementation is
  technical-code-complete for `public-diagnostic` evidence authority.
- `vinfast-acceptance` remains intentionally fail-closed. Migration `0022`
  rejects that authority class until an authenticated external human-witness
  registrar exists. This bounded authority stop is not a code defect and does
  not grant Product, Brand, Legal, Data, Privacy or Release acceptance.
- Independent risk review also found no VFBIZ-0192 P0. It identified downstream
  finding `VFBIZ-0192-R14-GOVERNANCE-BINDING-001`: the semantic evidence gate
  is not yet wired into the governance release resolver. This does not reopen
  the isolated evidence-authority implementation, but it blocks staging/public
  activation and is routed to VFBIZ-0211 through coordination request
  `coord-6573fa79-6bf9-4879-9b24-4233f96095cd`.
- Exact next action: retain review status for VinFast acceptance and continue
  only non-release development lanes that do not consume a
  `vinfast-acceptance` evidence digest.
- Downstream coordination
  `coord-6573fa79-6bf9-4879-9b24-4233f96095cd` is now responded and closed.
  VFBIZ-0211 binds the real release resolver to exact semantic Evaluation
  evidence and rejects `public-diagnostic`, forged recommendation and forged
  human-approval fields. This resolves the downstream wiring finding without
  widening VFBIZ-0192 authority or creating a VinFast acceptance witness.
- Revision-17 fresh PostgreSQL evidence run passed all 234 integration/evidence
  tests against a new disposable pgvector/PostgreSQL 17 container after
  upgrading through `20260802_0025`. The first reused-database attempt failed
  closed on an existing role and was discarded; no reused state is counted.
  This confirms migration/evidence behavior only and does not create the
  unavailable authenticated VinFast witness.

## Evidence

- [x] `npm run contracts:lint` — 38 registered AI contracts, 67 vectors and
  Python/Node canonical digest parity passed on 2026-07-31.
- [x] `npm run verify:ai` — Ruff, Pyright, 739 tests and Alembic offline replay
  passed on 2026-07-31; 98 external-profile tests were explicitly skipped.
- [x] Focused clean PostgreSQL 17 + pgvector migration replay from 0001 through
  0022 and all six definition/run/evidence authority integration tests passed
  on 2026-07-31, including restricted runner-role retry/revival attacks.
- [x] Focused PostgreSQL evidence execution — exact lease, malformed usage,
  expired-attempt accounting, plan-bound retry, plan/task/result/evidence
  mutation, delete/truncate, overspend, direct-ready, atomic seal and
  direct-insert tampering of human approval, completeness, authority class and
  request digest passed.
- [x] Revision-6 independent reviews completed and rejected with pinned P0/P1
  findings; P0 findings were remediated in revision 7.
- [x] P1 released-definition reachability, protected confidence bounds and
  runtime database role boundary implemented with focused tests.
- [x] Revision-8 P1 alias, plan-attempt, non-retryable expiry and Wilson parity
  findings reproduced and remediated with regression tests.
- [x] Final independent revision-12 reviews — no reproducible P0/P1; technical
  code-complete recommendation only, with human acceptance/release explicitly
  ungranted.
- [x] Revision-13 independent re-review confirmed the prior P0/P1 retry and
  revival findings are closed and identified the two revision-14 P1 findings.
- [x] Fresh PostgreSQL 17 + pgvector replay through `0022` and all six focused
  definition/run/evidence tests passed after the revision-14 fixes, including
  exhausted-budget no-dispatch and forged VinFast authority rejection.
- [ ] Revision-14 accountable technical acceptance is not yet granted.
- [x] Revision-15 independent technical verification — no P0/P1 reproduced;
  45 focused tests, fresh migrations `0001` through `0023`, seven PostgreSQL
  integration tests and contract lint passed. Recommendation is limited to
  `public-diagnostic` technical code-completeness.
- [ ] Authenticated external human-witness registrar and accountable VinFast
  acceptance remain unavailable; `vinfast-acceptance` stays fail-closed.
- [x] Independent risk review — no VFBIZ-0192 P0; downstream semantic release
  binding was routed to VFBIZ-0211 and remained an activation blocker until
  the authority-correct facade/resolver integration was independently closed.
- [x] Downstream semantic release binding coordination is closed with observed
  facade/resolver and PostgreSQL release-negative evidence. The separate
  authenticated external-witness and human-governance gates remain open.

### review — 2026-07-29T18:45:46Z

Implementation, canonical contracts and migration gates passed. Automated
evidence is code-complete; accountable Data/Release decisions remain human.

### review — 2026-07-31T18:18:00Z

Revision 12 received two independent technical code-complete recommendations.
Exact-rational calibration parity, strict `all` binding, micro-USD semantics,
persistable duration limits, fresh migration replay and release-negative gates
were observed. The item stays in review because no accountable human acceptance
or release decision is encoded by this work.

### review — 2026-07-31T18:30:00Z

A later independent runner-role audit reopened revision 12. Revision 13 binds
retry to a persisted result and usage ledger, makes terminal run states
immutable and adds real restricted-role regression coverage. Fresh migration
replay, six PostgreSQL modules, contracts lint, Ruff and Pyright pass; the item
remains in review pending independent confirmation of the exact reproductions.

### review — 2026-07-31T10:34:19Z

The revision-13 re-review closed the direct-retry and terminal-revival
reproductions but found budget-dispatch and suite-witness P1 gaps. Revision 14
now fails exhausted budgets before provider dispatch, binds remaining budgets
to every lease and refuses persisted VinFast acceptance authority until an
authenticated external witness registrar exists. Fresh database replay and
the full AI gate pass; accountable acceptance remains outstanding.

### review — 2026-08-01T10:38:06Z

Fresh independent revision-15 verification found no reproducible P0/P1 and
replayed the complete migration chain plus restricted authority integration
tests. Technical code-completeness is recommended only for
`public-diagnostic`. The exact `vinfast-acceptance` path remains correctly
blocked on an authenticated external witness registrar and separate accountable
human decisions.

Independent risk review agrees that an external registrar is not required for
the stated isolated technical outcome. A registrar becomes mandatory before a
real `vinfast-acceptance` suite can be registered. The separate downstream
release-resolver binding is tracked by coordination request
`coord-6573fa79-6bf9-4879-9b24-4233f96095cd`.

### implementation — 2026-08-03

The evaluation runtime now exposes explicit `queue`, `start`, `mark_grading`
and `mark_comparing` transitions plus a provider-neutral
`EvaluationQualificationRunner` that composes planning, registration,
materialization, fenced case execution and evidence sealing. No transition can
reach `decision_ready` without the existing sealed evidence authority. Ruff,
Pyright and the focused lifecycle/planning suite pass; external human authority
and live provider evidence remain ungranted.

### implementation — 2026-08-03 (operational producer)

The qualification presentation facade now exposes the same provider-neutral
runner as the application composition root. A handler receives only a fenced
case lease; it cannot seal evidence or promote a release. The full AI suite,
including the new lifecycle tests, passes locally. This is technical
code-completeness evidence only; no Product, Brand, Legal, Data/Privacy or
Release approval is inferred.

The DB profile was rerun against a newly created disposable PostgreSQL 17 /
pgvector container. Alembic upgraded a clean database through `20260802_0025`
and the complete integration/evidence selection exited successfully. A reused
container that already contained authority roles was not counted as evidence;
the temporary clean container was removed after the run.
