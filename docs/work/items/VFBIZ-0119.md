---
id: VFBIZ-0119
title: Align Assistant Release domain with canonical contract
status: done
mode: controlled
priority: P0
owner_team: ai-assurance
accountable_role: release-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/modules/governance/domain
  - backend/ai/tests/evaluation/governance
depends_on:
  - VFBIZ-0118
  - VFBIZ-0120
controlled_signals:
  - ai-release
  - grounding
exclusive_resources:
  - ai-assistant-release-manifest
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 7
review_date: "2026-07-26"
updated_at: "2026-07-26T06:37:30.221Z"
---

# Outcome

Assistant Release domain object round-trip đầy đủ canonical v3 contract, bao gồm
promotion evidence, activation-envelope digest và exact rollback activation.

## Constraints

- Domain không tin environment hash như release authority.
- Candidate digest và activation-envelope digest là hai identity khác nhau.
- Lifecycle state không được lưu trùng thành hai mutable sources.
- Không triển khai database repository hoặc provider binding trong lane này.

## Done when

- Domain model biểu diễn đầy đủ canonical contract mà không mất trường.
- Canonical digest tests có golden vectors xuyên Python/JSON Schema.
- Invalid rollback identity, digest, window và lifecycle bị từ chối.
- AI và governance checks đạt.

## Checkpoint

- Canonical v3 authority transaction đã fail-closed trên schema, digest chain,
  activation/revoke/rollback identity, pointer revision, chronology, effective
  window, static-safe coverage, history và outbox binding.
- Independent review không còn P0/P1 correctness blocker trong domain lane.
- Cross-language contract vectors, PostgreSQL history proof và legacy resolver
  cutover được chuyển cho các lane contract/persistence/repository sở hữu chúng.
- Exact next action: VFBIZ-0116 tạo immutable persistence/history và
  VFBIZ-0114 tích hợp one-way resolver từ authority v3.

## Evidence

- [x] `npm run verify:ai` — 263 passed, 4 integration tests được theo dõi bởi
  PostgreSQL CI gate; Ruff, Pyright và Alembic SQL đạt.
- [x] `npm run governance:check` — docs, reports, guides, authorization,
  WorkItemV2 và 61 context scenarios đạt.
- [x] Independent read-only architecture review — không còn P0/P1 correctness
  blocker; chronology regression và 26 focused tests đạt.
- [x] Commit `52d2c01` — canonical release authority domain và golden vectors.
