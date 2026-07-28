---
id: VFBIZ-0139
title: Bind released golden suites to AI release gate
status: proposed
mode: controlled
priority: P0
owner_team: ai-assurance
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai
  - contracts/ai
  - docs/work/items/VFBIZ-0139.md
  - WORK.md
depends_on:
  - VFBIZ-0133
controlled_signals:
  - ai-evaluation
  - ai-release
  - dataset-release
exclusive_resources:
  - ai-dataset-registry
  - ai-knowledge-release-registry
required_checks:
  - npm run verify:ai
  - npm run contracts:lint
  - npm run governance:check
revision: 1
review_date: "2026-08-28"
---

# Outcome

AI release activation chỉ chấp nhận immutable Dataset Release Manifest và
released golden-suite evidence đúng candidate/model/prompt/policy revision.

## Constraints

- Dataset/golden release không tự promote AI release.
- Rollback/tombstone phải fail closed trên runtime pointer.

## Done when

- Cross-revision, missing approval và contaminated suite đều bị activation gate từ chối.

## Checkpoint

- Exact next action: chờ VFBIZ-0134/0135 có released evidence thật.

## Evidence

- [ ] `npm run verify:ai` — add evidence reference
- [ ] `npm run contracts:lint` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
