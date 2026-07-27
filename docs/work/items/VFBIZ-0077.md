---
id: VFBIZ-0077
title: EV Journey Planner product, architecture và contracts
status: proposed
mode: controlled
priority: P0
owner_team: mobility-platform
accountable_role: architect
primary_workspace: root
affected_workspaces:
  - root
  - api
allowed_paths:
  - docs/product/ev-journey-planner.md
  - docs/architecture/ev-journey-planner.md
  - docs/decisions/0007-ev-route-and-charging-planner.md
  - backend/api/docs/trip-engine.md
  - contracts/openapi
  - docs/work/items/VFBIZ-0077.md
  - docs/work/plans/VFBIZ-0077.md
depends_on: []
controlled_signals:
  - architecture
  - ev-trip-planner
  - location-privacy
  - public-contract
  - route-provider
  - trip-correctness
exclusive_resources:
  - public-contract
required_checks:
  - npm run contracts:lint
  - npm run governance:check
plan: docs/work/plans/VFBIZ-0077.md
revision: 1
review_date: "2026-08-24"
---

# Outcome

Product, architecture, privacy, provider boundary và asynchronous API contract
của EV Journey Planner được khóa thành nguồn sự thật đủ để các lane
implementation không tự đưa ra quyết định khác nhau.

## Constraints

- Baseline chỉ tìm trạm và lập kế hoạch trước chuyến đi; không live navigation,
  vehicle telemetry hoặc safety-critical guidance.
- PostgreSQL/PostGIS giữ operational data; Google và V-GREEN nằm sau adapter.
- Không hứa độ chính xác hoặc SLO trước benchmark.
- Human Architect, Privacy, Legal và Product authority duyệt quyết định tương
  ứng; agent không tự chấp nhận risk hoặc provider terms.

## Done when

- PRD định nghĩa user journey, non-goal, KPI và failure experience.
- Architecture định nghĩa Location/EVSE/Connector, planner components, trust
  boundary, revision và retention.
- Public contract có asynchronous plan lifecycle, cancellation và typed failure.
- ADR ghi OCPI reference, Google policy boundary và location privacy.
- Threat scenarios và provider-policy checklist có owner và acceptance.

## Decisions and assumptions

- Dùng một ExecPlan chung để điều phối VFBIZ-0077 đến VFBIZ-0085.
- `mobility-platform` là owner; root Architecture chỉ giữ human decision gate.

## Checkpoint

- Exact next action: Product Owner và Architect review PRD/architecture scope
  trước khi lease `public-contract` được cấp.

## Evidence

- [ ] `npm run contracts:lint` — add observed evidence
- [ ] `npm run governance:check` — add observed evidence
