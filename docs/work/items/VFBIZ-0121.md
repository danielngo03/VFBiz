---
id: VFBIZ-0121
title: Harden chatbot Agent OS routing and ownership
status: done
mode: controlled
priority: P0
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - .agents/organization.json
  - tools/context-resolver.mjs
  - tools/lib/governance.mjs
  - tools/check-agent-governance.mjs
  - tests/governance
  - docs/work/items/VFBIZ-0121.md
  - WORK.md
depends_on: []
controlled_signals:
  - multi-agent
  - ai-release
  - provider-parity
exclusive_resources:
  - agent-organization-registry
required_checks:
  - npm run verify:governance
  - npm run governance:check
revision: 5
review_date: "2026-07-26"
updated_at: "2026-07-26T07:25:43.029Z"
---

# Outcome

Agent OS route đúng chatbot release/persistence work, cấp đúng owner và exclusive
lease, không cấp writer ngoài team boundary, và có deterministic evidence cho
review/provider parity trước khi mở các lane persistence/runtime.

## Constraints

- Không tạo role, agent hoặc skill mới.
- `database-migration` là canonical lease cho mọi Alembic/Prisma migration.
- OCC chỉ mang nghĩa `session-concurrency` khi có conversation/session/message,
  không áp dụng cho release pointer hoặc domain khác.
- Integration test path phải có đúng một owner team.
- Resolver chọn exact headings theo signal; giới hạn là trần, không phải quota.
- Reviewer read-only, worker không spawn worker và tối đa ba writer trực tiếp.

## Done when

- `backend/ai/tests/integration/platform` và `.../governance` có owner rõ ràng.
- Release persistence không route nhầm sang Customer Engagement vì chữ OCC.
- Release contract/persistence/repository/model/grounding/graph signals có exact
  context anchors và không nạp đủ quota khi không cần.
- Governance scenario chứng minh canonical migration lease, owner routing,
  controlled review profiles và bounded context.
- Provider-neutral governance và generated state checks đạt, không dirty tree.

## Checkpoint

- Exact next action: đóng work item sau khi lưu deterministic verification
  evidence và integration-owner fix cho assignment boundary.

## Evidence

- [x] `npm run verify:governance` — 71 provider-neutral scenarios, contracts,
  docs, reports, guides và generated adapters đạt tại `0d133d0`.
- [x] `npm run governance:check` — instruction budgets, work schemas, ownership,
  exact-heading bootstrap và assignment delivery đạt tại `0d133d0`.
- [x] Independent verifier — hai vòng review hoàn tất; integration owner sửa
  finding cuối về work-item path boundary trong `0d133d0`.
