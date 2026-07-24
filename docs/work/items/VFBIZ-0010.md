---
id: VFBIZ-0010
title: Chuẩn hóa Trip Planner release validation skill
status: done
mode: controlled
priority: P1
owner_team: mobility-platform
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/.agents/skills/validate-trip-release
depends_on: []
controlled_signals:
  - trip-release
exclusive_resources: []
required_checks:
  - governance
  - skill-validation
  - context-routing
revision: 5
review_date: "2026-08-23"
updated_at: "2026-07-22T18:25:43.221Z"
---

# Outcome

Trip Planner release validation dùng acceptance/SLO đang được duyệt thay vì
đóng băng threshold theo một sprint trong reusable skill.

## Constraints

- Không thay trip algorithm, API hoặc performance target hiện hành.

## Done when

- Skill pin source/provider revision và kiểm deterministic/failure/cost evidence.
- Threshold được lấy từ active work item/SLO policy; thiếu target thì dừng.
- Natural-language release request chọn đúng skill và Release Owner.

## Checkpoint

- Exact next action: loại threshold theo sprint khỏi durable skill.

## Evidence

- [x] `governance` — Trip release review route tới `mobility-platform` và Release Owner.
- [x] `skill-validation` — `quick_validate.py backend/api/.agents/skills/validate-trip-release` trả `Skill is valid!`.
- [x] `context-routing` — skill được chọn theo signal `trip-release`, không dùng ngưỡng hiệu năng hard-code; commit `3f238bb`.
