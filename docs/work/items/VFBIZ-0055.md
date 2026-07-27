---
id: VFBIZ-0055
title: Workforce authorization decision and capability contract
status: done
mode: controlled
priority: P0
owner_team: architecture-integration
accountable_role: architect
primary_workspace: root
affected_workspaces:
  - root
  - api
  - workforce-portal
allowed_paths:
  - .agents/organization.json
  - contracts/authorization
  - docs/decisions/0004-dynamic-workforce-authorization.md
  - docs/architecture/repository-blueprint.md
  - docs/architecture/system-context.md
  - docs/governance/security-data-ai.md
  - docs/product/capability-map.md
  - docs/product/roadmap.md
  - docs/work/items/VFBIZ-0055.md
  - docs/work/plans/VFBIZ-0055.md
  - README.md
  - tests/governance/scenarios.json
  - tools/lib/governance.mjs
  - WORK.md
depends_on: []
controlled_signals:
  - architecture
  - authorization
  - public-contract
exclusive_resources:
  - agent-organization-registry
  - public-contract
required_checks:
  - npm run governance:check
revision: 3
review_date: "2026-08-24"
updated_at: "2026-07-24T20:00:00.000+07:00"
---

# Outcome

Khóa ranh giới API-owned dynamic authorization, capability catalog nguyên tử,
maker-checker và Next.js Workforce Portal trước khi runtime implementation bắt
đầu.

## Constraints

- Keycloak chỉ sở hữu authentication, MFA và coarse workforce identity.
- Capability do code/contract định nghĩa; UI không tạo permission string.
- Role, assignment và organizational scope là dữ liệu động do API sở hữu.
- Không dùng wildcard hoặc một quyền `super-admin` vượt mọi policy.
- Workforce Portal quản trị role/assignment nhưng API vẫn là enforcement
  authority; OAuth scope không thay thế business capability.

## Done when

- ADR 0004 được ghi nhận từ quyết định đã được người dùng phê duyệt.
- Capability catalog và JSON Schema machine-readable hợp lệ.
- API/Portal work item có thể tham chiếu cùng một contract.

## Checkpoint

- ADR và capability contract đã khóa cho implementation.
- Exact next action: VFBIZ-0056 và VFBIZ-0057 triển khai hai lane tách biệt.

## Evidence

- [x] Capability JSON Schema — 23 key unique và schema-valid.
- [x] Provider-neutral governance routing — 56 scenarios đạt, gồm portal và
  API dynamic authorization.
- [x] Full `npm run governance:check` — đạt sạch trên 2026-07-27 (123 work
  item, provider adapters, skills, work schemas và 72 context scenarios);
  các work item phụ đã cập nhật và docs index đã sinh lại ở integration lane
  từ lâu, mục này chỉ chưa được tick lại sau khi điều kiện chờ đã hết.
