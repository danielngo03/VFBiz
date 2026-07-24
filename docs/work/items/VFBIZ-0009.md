---
id: VFBIZ-0009
title: Chuẩn hóa AI evaluation governance và release skill
status: done
mode: controlled
priority: P1
owner_team: ai-assurance
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/docs/evaluation-and-release.md
  - backend/ai/.agents/skills/validate-ai-release
depends_on: []
controlled_signals:
  - ai-evaluation
  - ai-release
exclusive_resources: []
required_checks:
  - governance
  - skill-validation
  - ai-release
revision: 5
review_date: "2026-08-23"
updated_at: "2026-07-22T18:25:42.911Z"
---

# Outcome

AI Assurance tạo evaluation/release evidence độc lập, tái lập được và không tự
approve hoặc promote candidate.

## Constraints

- Không sửa threshold/runtime gate trong work item docs này.
- Hard safety gate và quality threshold phải được phân biệt rõ.

## Done when

- Doc mô tả held-out suite, contamination, evaluator independence và evidence hash.
- Citation/ACL/PII hard gate không bị diễn đạt như threshold mềm.
- Skill so sánh baseline, kiểm repeatability và chỉ trả immutable report.
- Routing chọn đúng `ai-assurance` và release authorities.

## Checkpoint

- Exact next action: viết evaluation/release doc và cập nhật validation skill.

## Evidence

- [x] `governance` — AI release review route tới `ai-assurance` và ba human authorities.
- [x] `skill-validation` — `quick_validate.py backend/ai/.agents/skills/validate-ai-release` trả `Skill is valid!`.
- [x] `ai-release` — held-out, contamination, repeatability và release evidence được tách; commit `3d8def4`.
