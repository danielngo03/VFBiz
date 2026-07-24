---
id: multi-agent-and-review
title: Multi-agent execution và review policy
status: active
owner_role: engineering-lead
scope: root
when_to_read:
  - delegation
  - parallel
  - verification
  - review
tags:
  - agents
  - review
  - anti-loop
revision: 2
review_date: 2026-09-01
supersedes:
  - multi-agent
  - review-policy
  - agent-execution-control
---

# Multi-agent execution and review

The organizational hierarchy is logical. Runtime execution remains shallow:
one orchestrator and at most three direct workers. A worker cannot delegate.

## Chọn docs, skill, agent, plugin hay hook

| Cơ chế | Dùng cho | Không dùng làm |
| --- | --- | --- |
| `AGENTS.md` | Rule bền vững, boundary, command và Definition of Done gần workspace | Product backlog hoặc tài liệu kiến trúc dài |
| Docs/ADR/contract | Product/architecture/policy và quyết định có owner/revision | Transcript hoặc instruction luôn preload |
| Work item/ExecPlan | Trạng thái delivery, acceptance, checkpoint và kế hoạch dài | Rule dùng lại cho mọi task |
| Skill | Một workflow lặp lại, trigger/đầu ra/validation ổn định | Kho kiến thức chung hoặc constraint theo sprint |
| Runtime role | Tool/permission/context profile cho một assignment | Chức danh, phòng ban hoặc approval authority |
| Plugin/MCP | Truy cập hệ thống hoặc dữ liệu live được allowlist | Nguồn truth bắt buộc hay business rule duy nhất |
| Hook/CI guard | Kiểm tra deterministic, nhanh và không tự loop | Lập luận, retry hoặc orchestration nền |

Provider-native skill/plugin là accelerator tùy chọn. Workflow cốt lõi vẫn phải
chạy được từ canonical `AGENTS.md`, `SKILL.md`, work envelope và repository
scripts để Codex, Claude, Gemini hoặc generic client nhận cùng authority.

## When to delegate

Delegate independent exploration, high-volume test/log analysis, competing
hypotheses, focused risk review or writer lanes with disjoint paths. Stay with
one agent for small edits, iterative work or phases sharing significant context.

Every assignment declares work ID, objective, working directory, allowed paths,
required context, deliverable, acceptance, tools, turn/timeout budget and stop
conditions. Workers return a short report with changed paths, evidence, risks
and one next action.

## Claims and leases

- Fast and single-writer bounded work do not need a claim.
- Delegated writers, controlled work and parallel work require a claim.
- Each parallel writer uses a separate worktree.
- Public contracts, migrations, dependency lockfiles, Drupal config and AI
  dataset registries require exclusive leases.
- Claim overlap, stale base revision or expired fencing token fails safely.

Provider hooks call the same deterministic repository guards. CI and repository
policy remain the authority.

## Coordination and escalation

Contact only the team owning the needed interface. Send the shared outcome,
known facts, exact dependency, requested artifact, blocking state and safe
default. Do not forward full chat history.

Escalations contain signal, impact, evidence, at most three options,
recommendation, decision owner and blocking condition. Do not repeat an
escalation without new evidence.

## Verification and review

| Mode | Required evidence |
| --- | --- |
| Fast | One focused check or visual observation |
| Bounded | Focused checks; independent reviewer only for observable behavior or explicit risk |
| Controlled | Verifier, relevant risk/domain review and human gate |
| Release | CI, operational evidence, rollback and Release Owner decision |

Reviewers are read-only. Findings include severity, fingerprint, path/evidence,
impact and disposition. Reject duplicate and preference-only findings.

Retry the same cause at most twice. Review/fix stops after two cycles. Without
new evidence, return `needs-decision` or `failed-safely`; never loop.
