---
id: VFBIZ-0001
title: Chuẩn hóa repository đa-agent độc lập provider
status: done
mode: controlled
priority: P1
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
  - api
  - customer-portal
  - workforce-portal
allowed_paths:
  - AGENTS.md
  - CLAUDE.md
  - PLANS.md
  - WORK.md
  - .agents
  - .codex
  - .claude
  - .gemini
  - docs
  - contracts/governance
  - tools
  - tests/governance
  - package.json
  - package-lock.json
  - .gitignore
  - .github
  - SECURITY.md
  - redocly.yaml
  - backend/AGENTS.md
  - backend/CLAUDE.md
  - backend/api/AGENTS.md
  - backend/api/CLAUDE.md
  - backend/api/.agents
  - backend/api/.claude
  - backend/api/test/contract/openapi.spec.ts
  - backend/ai/AGENTS.md
  - backend/ai/CLAUDE.md
  - backend/ai/.agents
  - backend/ai/.claude
  - drupal/AGENTS.md
  - drupal/CLAUDE.md
  - mobile/AGENTS.md
  - mobile/CLAUDE.md
  - apps/customer-portal/AGENTS.md
  - apps/customer-portal/CLAUDE.md
  - apps/customer-portal/package.json
  - apps/customer-portal/tsconfig.json
  - apps/workforce-portal/AGENTS.md
  - apps/workforce-portal/CLAUDE.md
  - apps/workforce-portal/package.json
  - apps/workforce-portal/tsconfig.json
  - infra/AGENTS.md
  - infra/CLAUDE.md
  - contracts/openapi
depends_on: []
controlled_signals:
  - agent-control
  - provider-adapter
  - governance-contract
exclusive_resources:
  - dependency-lockfile
required_checks:
  - governance
  - provider-parity
  - context-budget
plan: docs/work/plans/VFBIZ-0001.md
revision: 4
review_date: "2026-08-22"
updated_at: "2026-07-22T17:51:53.668Z"
---

# Outcome

Codex, Claude, Gemini và generic coding clients có thể nhận cùng work item,
context, skills, claims và evidence từ Git mà không phụ thuộc provider memory
hoặc một hệ thống quản lý công việc bên ngoài.

## Constraints

- Không sửa runtime behavior của API, AI, Drupal, mobile hoặc apps.
- Không reset 1.270 path thay đổi đã được bảo toàn tại checkpoint commit
  `680aa5c5443ad65c703c4a742f0f286214d44548` trên branch
  `agent/VFBIZ-0001`.
- Không thực hiện thao tác quản trị trên hệ thống công việc từ xa; người dùng tự
  xử lý ngoài repository.
- Không tự nhận human approval hoặc production readiness.

## Done when

- Git-native work CLI và generated views hoạt động.
- Instruction chain và context budgets đạt gate.
- Skills/roles/provider adapters có một canonical source.
- Claim/hook behavior không tạo ceremony cho `fast`/single-writer `bounded`.
- Không còn dependency quản trị công việc cũ trong working tree hoặc current refs.
- Governance and parity tests pass with observed output.

## Checkpoint

- Original base revision: `f108903ea80f651ba821f1461ea18ccfee814695`.
- WIP manifest SHA-256:
  `87c9767eb038ef254072260dce834a3cbee92b24d99e8cef37635405715c16e6`.
- Preservation checkpoint: `680aa5c5443ad65c703c4a742f0f286214d44548`.
- Current action: all governance and workspace gates are observed passing.
- Exact next action: commit the accepted governance baseline and open future
  runtime work as separate work items.

## Evidence

- [x] `governance` — `npm run verify` passed on 2026-07-23: WorkItemV2,
  20-process ID allocation, transitions, dependencies, stale locks, 3-writer
  cap, collision/lease/fencing, Git-verified handoff, API, apps, AI and Drupal.
- [x] `provider-parity` — 18 routing scenarios produced invariant results for
  Codex, Claude, Gemini and generic adapters; Codex project config loaded under
  strict isolated doctor, Claude doctor passed, and Gemini config/schema was
  validated while its CLI is not installed on this machine.
- [x] `context-budget` — observed fast=0 docs/0 skills, bounded=1 exact heading,
  controlled=4 exact headings/2 skills; generic bootstrap emitted the same
  ownership, authority, assignment and source hashes.

### done — 2026-07-22T17:51:53.668Z

Acceptance hoàn tất trên staging foundation; không phải production release.
