---
id: VFBIZ-0007
title: Chuẩn hóa docs và tool workflow AI Platform
status: done
mode: controlled
priority: P1
owner_team: ai-platform-foundation
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/AGENTS.md
  - backend/ai/README.md
  - backend/ai/docs/architecture.md
  - backend/ai/docs/security-profiles-and-release.md
  - backend/ai/docs/safety-and-abuse.md
  - backend/ai/.agents/skills/register-ai-tool
depends_on: []
controlled_signals:
  - ai-tool
  - ai-release
exclusive_resources: []
required_checks:
  - governance
  - skill-validation
  - ai-safety
revision: 5
review_date: "2026-08-23"
updated_at: "2026-07-22T18:25:42.255Z"
---

# Outcome

AI Platform Foundation có boundary và tài liệu an toàn rõ cho serving,
assistant, tool proposal, profile isolation và abuse controls.

## Constraints

- Không thay runtime FastAPI, model contract, schema hoặc release candidate.
- Security policy root là baseline; local docs chỉ cụ thể hóa implementation.

## Done when

- AGENTS nêu rõ separation giữa builder, evaluator và release authority.
- Architecture không gộp dataset/evaluation ownership vào runtime team.
- Safety/abuse doc có hard gates, incident, kill switch và exception owner.
- `register-ai-tool` không chứa scope theo sprint và không tự publish tool.

## Checkpoint

- Exact next action: tách AI platform/safety guidance khỏi tài liệu gộp hiện tại.

## Evidence

- [x] `governance` — `npm run governance:check` đạt với ownership disjoint.
- [x] `skill-validation` — `quick_validate.py backend/ai/.agents/skills/register-ai-tool` trả `Skill is valid!`.
- [x] `ai-safety` — builder/evaluator/release authority được tách trong `safety-and-abuse.md`; commit `4b43256`.
