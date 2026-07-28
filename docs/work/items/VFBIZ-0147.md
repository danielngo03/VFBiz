---
id: VFBIZ-0147
title: Refactor Dataset runtime dependency boundaries
status: active
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai/app/modules/datasets
  - backend/ai/tests/architecture
  - backend/ai/tests/unit/datasets
  - backend/ai/tests/integration/datasets
  - backend/ai/docs/dataset-engineering.md
  - docs/work/items/VFBIZ-0147.md
  - WORK.md
depends_on:
  - VFBIZ-0146
controlled_signals:
  - ai-dataset
  - dataset-release
exclusive_resources:
  - ai-dataset-registry
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 4
review_date: "2026-08-28"
updated_at: "2026-07-28T11:19:19.925Z"
---

# Outcome

Move Dataset Platform network, filesystem, scanner, format and CLI mechanics
behind application ports so the runtime enforces the V11.2 dependency boundary
without changing dataset lifecycle behavior or approval state.

## Constraints

- Preserve the active Chatbot, source intake and Golden-case WIP.
- Do not mutate downloaded payloads, observed hashes, approvals or registry state.
- Create a directory only when the same change adds a concrete consumer.
- Domain and application remain independent of HTTPX, subprocess, filesystem
  implementation, SQLAlchemy, GCS SDK and CLI parsing.

## Done when

- Source intake depends on source-reader, scanner, object-store and registry ports.
- HTTP/network, archive/file-format, local/GCS storage and scanner implementations
  live under infrastructure.
- CLI and worker entrypoints only map input and invoke application use cases.
- Architecture tests reject forbidden Dataset application imports and cross-context
  deep imports.
- Existing unit/integration behavior remains compatible.

## Checkpoint

- Existing VFBIZ-0130/0132 Chatbot changes are outside this work item's paths and
  remain untouched.
- Exact next action: split application ports and relocate source/scanner/format
  implementations with compatibility imports for one revision.

## Evidence

- [ ] `npm run verify:ai` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference

### active — 2026-07-28T11:05:47.568Z

Begin controlled Dataset runtime boundary refactor; preserve unrelated Chatbot and payload WIP.

### active — 2026-07-28T11:19:19.925Z

Dataset application boundary refactored behind ports; 435 AI tests pass. Remaining: migrate legacy inspect_datasets presentation script under owned path, add central architecture enforcement, then rerun governance after docs index reconciliation.
