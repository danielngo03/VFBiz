---
id: VFBIZ-0077-plan
title: ExecPlan EV Journey Planner
status: proposed
owner_role: engineering-lead
scope: cross-system
when_to_read:
  - VFBIZ-0077
  - VFBIZ-0078
  - VFBIZ-0079
  - VFBIZ-0080
  - VFBIZ-0081
  - VFBIZ-0082
  - VFBIZ-0083
  - VFBIZ-0084
  - VFBIZ-0085
  - ev-trip-planner
  - trip-release
context_anchors:
  VFBIZ-0077: "## Progress"
  ev-trip-planner: "## Implementation phases and allowed paths"
  trip-release: "## Validation and observed evidence"
tags:
  - ev-trip-planner
  - charging-data
  - route-provider
  - location-privacy
revision: 2
review_date: 2026-08-24
supersedes: []
---

# ExecPlan — EV Journey Planner

## Purpose and observable outcome

Deliver một EV Journey Planner pre-trip có data model chuẩn, provider boundary,
deterministic energy/charging computation, asynchronous API, accessible customer
experience và release evidence. Kết quả không được mô tả như live navigation.

## Scope, boundaries and non-goals

Trong phạm vi:

- Product/architecture/contract, charging data, provider adapters, energy
  estimator, constrained planner, Customer Portal và read-only chatbot tool.
- PostgreSQL/PostGIS operational data; Google/V-GREEN sau ports.
- Location privacy, FinOps, failure behavior và governed release.

Ngoài phạm vi:

- Vehicle telemetry, live rerouting/navigation, Kafka, federated learning,
  custom Go/Rust router, ML energy model và side-effect AI tools.

## Progress

- [ ] VFBIZ-0077 — product, architecture, threat model và contracts.
- [ ] VFBIZ-0078 — Location/EVSE/Connector/Tariff migration.
- [ ] VFBIZ-0079 — projection, source adapters và discovery API.
- [ ] VFBIZ-0080 — Google adapters và cost/privacy controls.
- [ ] VFBIZ-0081 — deterministic energy estimator.
- [ ] VFBIZ-0082 — constrained planner và asynchronous jobs.
- [ ] VFBIZ-0083 — Customer Portal experience.
- [ ] VFBIZ-0084 — `plan_ev_trip` integration.
- [ ] VFBIZ-0085 — evaluation và release evidence.

Do not mark progress complete without an observed command, artifact revision or
human evidence link.

Checkpoint 2026-07-24:

- Product, architecture, ADR, Trip Engine, Mobility instructions và combined
  Customer AI/EV threat model đã được materialize.
- Agent routing/work schema/skill metadata đã được cập nhật và kiểm tra.
- VFBIZ-0077 chưa hoàn tất vì machine-readable public contract và named human
  Architecture/Privacy/Legal review chưa có evidence.
- VFBIZ-0078 không được start trước dependencies `VFBIZ-0033`,
  `VFBIZ-0037` và `VFBIZ-0077`.
- Exact next action: Product Owner, Architect, Privacy và Legal review
  VFBIZ-0077; sau đó chuyển item qua `ready` và cấp `public-contract` lease.

## Surprises and discoveries

- Current charging schema aggregates connector counts; migration must not infer
  fabricated EVSE/Connector identities from that count.
- Existing work IDs 0075 and 0076 are already allocated; this plan starts at
  0077.
- Current `main` passes API typecheck and 195 unit tests; the reported
  VFBIZ-0005 compile failure is historical, not a current prerequisite.

## Decision log

- 2026-07-24 — Architecture: organize the capability by Experience,
  Application/Integration, AI Runtime and Control/Assurance planes.
- 2026-07-24 — Product: v1 is station discovery and pre-trip planning only.
- 2026-07-24 — Architecture: keep the solver in NestJS Mobility until profiling
  proves a separate runtime is required.
- 2026-07-24 — Data: use OCPI as an interoperability reference, not as the
  internal domain model.
- 2026-07-24 — Privacy: exact origin/destination is sensitive data with
  explicit retention and log-redaction controls.

Human approval is still required for product, architecture, provider terms,
privacy risk and release.

## Implementation phases and allowed paths

1. **Contract phase:** VFBIZ-0077 alone holds `public-contract`.
2. **Data/provider phase:** VFBIZ-0078 holds `database-migration`; VFBIZ-0080
   may run in parallel because it does not edit migration or public contract.
3. **Computation phase:** VFBIZ-0079 and VFBIZ-0081 use disjoint charging and
   energy paths. Integration owner seals both before VFBIZ-0082.
4. **Experience phase:** VFBIZ-0083 consumes sealed generated contracts.
5. **AI integration/release:** VFBIZ-0084 then VFBIZ-0085.

At most three direct workers. One path has one writer. Contract, migration,
lockfile and provider-policy decisions require explicit leases/authority.

## Validation and observed evidence

Required evidence is defined by each work item. The release report must include:

- Schema/migration replay and rollback.
- Unit/property/integration/E2E evidence.
- Zero, one, multiple and no-feasible-route scenarios.
- Provider timeout/quota/malformed response and record/replay load.
- Location redaction/retention and authorization negatives.
- SOC MAE, conservative underprediction, calibration, reserve violation,
  latency and provider cost measured against versioned acceptance.

Observed 2026-07-24:

- `npm run test:governance` — đạt; 75 canonical documents, 82 WorkItemV2 và
  61 provider-neutral routing scenarios.
- `npm run verify:api` — đạt; lint, typecheck, 195 unit tests, 61 E2E tests,
  Prisma validation và Nest build.
- `npm run verify:ai` — đạt; Ruff, Pyright, 25 Pytest cases và Alembic SQL
  dry-run.
- `git diff --check` — đạt.

Các lệnh trên chỉ chứng minh governance/foundation không regression; chúng
không phải Trip Planner runtime hoặc release evidence.

## Rollback and recovery

- Contract changes remain additive until consumer parity is proven.
- Charging migration uses expand/backfill/verify/contract phases.
- Provider adapter has kill switch and typed unavailable fallback.
- Data/algorithm/provider revisions are pinned per TripPlan.
- Candidate revisions can be withdrawn without deleting audit history.
- Customer UI must preserve a safe unavailable state during rollback.

## Outcomes and retrospective

Complete after VFBIZ-0085 records staging evidence and human decision. Capture
which assumptions failed, measured accuracy/cost, residual risks and the exact
criteria for considering live navigation, telemetry or a separate router.
