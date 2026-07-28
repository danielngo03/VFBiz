---
id: VFBIZ-0162
title: Add governed Dataset and Golden Review Board
status: active
mode: controlled
priority: P0
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
  - ai
allowed_paths:
  - .agents
  - .codex
  - .claude
  - .gemini
  - tools
  - tests/governance
  - docs/operating-model
  - docs/work/items/VFBIZ-0162.md
  - WORK.md
depends_on: []
controlled_signals:
  - agent-control
  - ai-evaluation
  - dataset-release
exclusive_resources:
  - agent-organization-registry
required_checks:
  - npm run verify:governance
  - npm run adapters:check
revision: 4
review_date: "2026-08-28"
updated_at: "2026-07-28T13:25:49.240Z"
---

# Outcome

Create a governed three-seat Dataset and Golden Review Board whose independent
agents produce immutable technical recommendations while named human authorities
retain adjudication and release authority.

## Constraints

- Add only one new canonical role: `golden-domain-reviewer`; reuse the existing
  dataset-quality and risk reviewers.
- Agents can recommend, reject or escalate; they cannot populate human approval
  evidence or activate a dataset/suite release.
- Author/generator cannot review; provider or model diversity alone is not
  reviewer independence.
- Missing seat, stale digest, disagreement or blocker fails closed.

## Done when

- Controlled Golden/Dataset review routes exactly three read-only expert seats.
- Routing selects AI Assurance ownership, correct review profiles and human
  authorities without falling back to `onboard-dataset` for evaluation-only work.
- Generated Codex/Claude/Gemini adapters remain read-only and match the canonical role.
- Deterministic scenarios reject self-review, duplicate run/claim seats, missing
  quorum, stale evidence and agent-authored human approval.
- Workspaces and scripts have explicit ownership instead of unowned runtime paths.

## Checkpoint

- Existing Golden v2 contains 100 pending smoke cases and zero human-adjudicated
  cases; this work does not fabricate completion.
- Exact next action: add the canonical domain reviewer, board routing and negative
  governance scenarios, then regenerate provider adapters.

## Evidence

- [ ] `npm run verify:governance` — focused governance passes; full gate awaits docs index regeneration
- [x] `npm run adapters:check` — passed 2026-07-28; generated provider adapters match the canonical organization
- [x] `node tools/check-agent-governance.mjs` — passed 2026-07-28 with 75 provider-neutral scenarios and negative Review Board vectors
- [x] independent read-only re-review — PASS after origin identities were bound into the canonical Board digest

### Review remediation — 2026-07-28

- Delivery work carrying `dataset-release` retains scoped writer roles; the
  three-seat Board is selected only for review or explicit Board signals.
- Golden suite paths and natural review wording both trigger the Board.
- Deterministic vectors reject self-review, duplicate runs/claims, missing
  seats, stale digests, disagreement and agent-authored human approval.
- Every seat requires actor/run/claim identity, immutable evidence digest and
  validity window; the board emits a canonical digest over recommendations.
- Author and generator identity envelopes are mandatory; human approval is a
  separate authority envelope and is rejected from agent Board evidence.
- Evaluation suites no longer acquire the source catalog lease.

### active — 2026-07-28T11:20:03.596Z

Implement three-seat agent review board while preserving human final authority.

### active — 2026-07-28T13:25:49.240Z

Three-seat Dataset and Golden Review Board now routes correctly and fails closed on self-review, quorum, digest, independence and human-authority violations. Independent re-review PASS. Exact next action: regenerate docs index under docs authority, run full governance gate, then move to review.
