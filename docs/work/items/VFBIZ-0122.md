---
id: VFBIZ-0122
title: Enforce shell-safe claims and review completion
status: active
mode: controlled
priority: P0
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - .codex/hooks.json
  - .claude/settings.json
  - .gemini/settings.json
  - tools/agent-hook.mjs
  - tools/lib/governance.mjs
  - tools/lib/agent-control.mjs
  - tools/work.mjs
  - tools/check-agent-control.mjs
  - tools/check-agent-governance.mjs
  - tests/governance
  - docs/work/items/VFBIZ-0122.md
  - WORK.md
depends_on: []
controlled_signals:
  - agent-control
  - security
exclusive_resources:
  - agent-organization-registry
required_checks:
  - verify:governance
  - governance:check
revision: 6
review_date: "2026-07-26"
updated_at: "2026-07-26T10:36:34.538Z"
---

# Outcome

Mọi writer chạy qua Codex, Claude hoặc Gemini đều bị giới hạn bởi claim khi
shell/formatter/codegen làm thay đổi Git state; controlled work không thể đóng
khi thiếu review ledger hợp lệ hoặc còn finding chưa được disposition.

## Constraints

- Giữ provider adapters mỏng; mọi provider hook gọi cùng repository guard.
- Không chặn command read-only hoặc thay đổi đã tồn tại trước invocation.
- Pre-hook phải chặn command phá hủy rộng; post-hook so sánh delta để bắt create,
  edit, rename và delete do shell tạo ra.
- Reviewer vẫn read-only; review/fix tối đa hai vòng và finding trùng không có
  evidence mới tiếp tục bị từ chối.
- Không thêm role, skill hoặc recursive auto-continue.

## Done when

- Codex `Bash`, Claude `Bash` và Gemini `run_shell_command` đều đi qua cùng
  claim-aware pre/post guard.
- Shell mutation ngoài `allowed_paths` hoặc thiếu active claim bị từ chối và có
  evidence xác định path vi phạm.
- Delta guard không quy nhầm pre-existing user changes cho invocation hiện tại.
- Controlled/parallel `work:done` yêu cầu verifier hoặc risk-review ledger phù
  hợp và từ chối khi còn finding mở.
- Governance tests bao phủ formatter/codegen mutation, rename/delete, command
  read-only, duplicate finding và review cycle limit.
- Generated adapters/checks không làm dirty worktree.

## Checkpoint

- Shell hooks now take invocation-scoped Git snapshots, compare worktree/index
  fingerprints and HEAD deltas, then validate only paths changed by that
  invocation.
- Codex `Bash`, Claude `Bash` and Gemini `run_shell_command` call the same
  provider-neutral guard.
- Controlled/parallel completion now requires completed verifier evidence,
  focused risk-review evidence when controlled signals require it, and no
  current open findings.
- Multi-lease renewal validates the current claim fencing token without
  incorrectly requiring every older held lease to carry that same token.
- Embedding provider/runtime work now routes to AI Model Platform with
  security, resilience, cost, data and release review. Grounding runtime adds
  security review.
- Exact heading anchors are authoritative and no longer cause the resolver to
  fill unused context budget with unrelated documents.
- Exact next action: independent read-only review of the routing delta.

## Evidence

- [x] `verify:governance` — passed locally on 2026-07-26; includes shell
  create/edit/rename/delete, pre-existing change, missing claim, review ledger,
  duplicate finding, cycle limit and multi-lease renewal coverage.
- [x] `governance:check` — passed locally on 2026-07-26 with 72
  provider-neutral routing scenarios and generated adapter drift checks.

### review — 2026-07-26T10:35:33.644Z

Independent review passed; shell mutation and review-ledger governance gates verified

### blocked — 2026-07-26T10:36:34.093Z

New independent evidence: embedding/provider-cost and grounding-runtime routing omit required AI Model, security, resilience and cost review profiles

### active — 2026-07-26T10:36:34.538Z

Reopened to correct signal routing and exact document anchors using new audit evidence
