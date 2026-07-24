---
id: VFBIZ-0008
title: Chuẩn hóa knowledge data governance và dataset skill
status: done
mode: controlled
priority: P1
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/docs/knowledge-data-governance.md
  - backend/ai/.agents/skills/onboard-dataset
depends_on: []
controlled_signals:
  - ai-dataset
  - data-governance
exclusive_resources:
  - ai-dataset-registry
required_checks:
  - governance
  - skill-validation
  - data-governance
revision: 5
review_date: "2026-08-23"
updated_at: "2026-07-22T18:25:42.612Z"
---

# Outcome

Knowledge/Data team có lifecycle chuẩn cho knowledge, evaluation và red-team
dataset với provenance, ACL, retention, quality và release evidence.

## Constraints

- Không onboard dữ liệu thật hoặc thay đổi registry/runtime.
- Data Owner/Privacy/Legal vẫn là human authority; agent chỉ chuẩn bị evidence.

## Done when

- Local doc phân biệt ba loại dataset và lifecycle/tombstone của chúng.
- Skill dùng ngôn ngữ prepare/validate/submit, không approve/release.
- Skill có stop condition cho rights, PII, ACL và contamination.
- Routing chọn đúng `ai-knowledge-engineering`, authorities và dataset lease.

## Checkpoint

- Exact next action: viết data lifecycle doc và chuẩn hóa dataset skill.

## Evidence

- [x] `governance` — dataset request route tới `ai-knowledge-engineering` và Data Owner.
- [x] `skill-validation` — `quick_validate.py backend/ai/.agents/skills/onboard-dataset` trả `Skill is valid!`.
- [x] `data-governance` — context chỉ nạp đúng heading về loại dataset và security baseline; commit `e33aad2`.
