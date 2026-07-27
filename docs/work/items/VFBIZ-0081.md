---
id: VFBIZ-0081
title: Energy estimator và uncertainty calibration
status: proposed
mode: controlled
priority: P0
owner_team: mobility-platform
accountable_role: data-owner
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/mobility/domain/energy
  - backend/api/src/modules/mobility/application
  - backend/api/test/unit/mobility
  - backend/api/test/fixtures/mobility
  - docs/work/items/VFBIZ-0081.md
  - docs/work/plans/VFBIZ-0077.md
depends_on:
  - VFBIZ-0033
  - VFBIZ-0077
  - VFBIZ-0078
controlled_signals:
  - energy-model
  - trip-correctness
exclusive_resources: []
required_checks:
  - npm run test --workspace @vfbiz/api -- mobility
  - npm run verify:api
plan: docs/work/plans/VFBIZ-0077.md
revision: 1
review_date: "2026-08-24"
---

# Outcome

Energy estimator deterministic trả expected/conservative range và calibration
evidence từ versioned VehicleEnergyProfile, không trình bày độ chính xác giả.

## Constraints

- Input unit rõ ràng; không để LLM tính SOC, energy hoặc charging duration.
- Xét temperature, elevation, wind, HVAC, payload và battery degradation khi
  dữ liệu tồn tại; thiếu input phải tăng uncertainty.
- Không phát hành model/coefficients thiếu source, effective date hoặc revision.

## Done when

- Property tests bảo vệ unit, monotonicity, reserve và physical bounds.
- Golden fixtures bao phủ đô thị, cao tốc, đèo, nóng/lạnh và degraded battery.
- Metrics gồm SOC MAE, conservative underprediction và calibration error.
- Low-confidence result có typed warning, không bị làm tròn thành certainty.

## Decisions and assumptions

- Baseline dùng deterministic coefficients; ML chỉ mở bằng work item/ADR khác.

## Checkpoint

- Exact next action: Data Owner duyệt energy-profile fixture và metric protocol.

## Evidence

- [ ] `npm run test --workspace @vfbiz/api -- mobility` — add observed evidence
- [ ] `npm run verify:api` — add observed evidence
