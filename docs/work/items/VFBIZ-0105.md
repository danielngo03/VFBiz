---
id: VFBIZ-0105
title: Align AI Model Platform ownership and review routing
status: done
mode: controlled
priority: P0
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
  - ai
allowed_paths:
  - .agents/organization.json
  - tools/lib/governance.mjs
  - tools/check-agent-governance.mjs
  - tests/governance
  - docs/INDEX.md
  - docs/INDEX.json
  - docs/work/items/VFBIZ-0105.md
  - WORK.md
depends_on: []
controlled_signals:
  - ai-release
  - model-routing
  - provider-fallback
  - ai-finops
exclusive_resources: []
required_checks:
  - npm run governance:check
revision: 5
review_date: "2026-07-25"
updated_at: "2026-07-25T14:47:00.728Z"
---

# Outcome

Controlled AI delivery có thể claim đúng các path đã được work item cho phép và
luôn nhận đủ security, resilience, cost, privacy và AI-safety review profile.

## Constraints

- Không mở ownership của AI Model Platform sang workspace hoặc capability không
  liên quan.
- Test và configuration path chỉ được cấp cho đúng bounded AI Model Platform
  workflow; không dùng wildcard toàn repository.
- Context resolver vẫn giữ trần tài liệu và không tự lấp đầy quota.

## Done when

- VFBIZ-0099 có thể acquire scoped-write claim cho implementation, config và
  test paths canonical mà không vượt team boundary.
- `model-routing`, `provider-fallback`, `ai-finops`, `grounding` và `ai-release`
  chọn đúng review profiles.
- Governance scenario chứng minh graph runtime không nạp tài liệu không cần
  thiết chỉ để đạt max-doc budget.
- Agent governance và work-item validation đạt.

## Checkpoint

- Exact next action: thêm failing governance scenarios cho ownership và review
  routing trước khi sửa registry/resolver.

## Evidence

- [x] `npm run governance:check` — passed on 2026-07-25; 61
  provider-neutral scenarios and all deterministic governance gates passed.

### ready — 2026-07-25T14:17:00.881Z

Outcome, ownership boundary and deterministic governance acceptance are defined.

### active — 2026-07-25T14:17:01.163Z

Starting TDD governance correction before AI runtime implementation.

### review — 2026-07-25T14:47:00.598Z

Ownership and review routing corrections verified by the full governance gate.

### done — 2026-07-25T14:47:00.728Z

Canonical ownership, review profiles and generated index ownership are enforced.
