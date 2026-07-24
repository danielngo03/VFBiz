---
id: VFBIZ-0068
title: Harden Agent OS và context routing cho các portal
status: done
mode: controlled
priority: P0
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
  - customer-portal
  - workforce-portal
allowed_paths:
  - .agents
  - .codex
  - .claude
  - .gemini
  - contracts/governance
  - tools
  - tests/governance
  - docs/work/items/VFBIZ-0068.md
  - WORK.md
depends_on: []
controlled_signals:
  - agent-governance
  - customer-bff
exclusive_resources:
  - agent-role-registry
  - provider-adapters
required_checks:
  - npm run governance:check
revision: 3
review_date: "2026-08-24"
updated_at: "2026-07-24T08:01:20.586Z"
---

# Outcome

Mọi provider nhận cùng assignment, role, skill, review profile và context delta;
controlled work không thể được cấp writer khi thiếu work item hợp lệ.

## Constraints

- Provider adapters không được chứa business rule riêng.
- Worker không được delegate và reviewer giữ quyền read-only.
- Context budget, review limit và tối đa ba writer hiện hành không được nới rộng.

## Done when

- Portal docs được resolver index và chọn bằng exact anchors.
- Visual-only change không bị phân loại auth; auth/session paths luôn controlled.
- Generic bootstrap chứa canonical role và tối đa hai skill body.
- Read-only adapters không có đường ghi qua shell.
- Coordination Request có CLI lifecycle; resume chỉ phát source đã đổi.

## Checkpoint

- Portal docs, exact anchors, review profiles, provider-neutral bootstrap and coordination lifecycle are implemented.
- Read-only provider roles are shell-restricted and controlled work without a valid work item is denied.
- Exact next action: use the hardened resolver and coordination lifecycle for VFBIZ-0069 onward.

## Evidence

- [x] `npm run governance:check` passed with 64 docs, 69 work items and 60 provider-neutral context scenarios.
