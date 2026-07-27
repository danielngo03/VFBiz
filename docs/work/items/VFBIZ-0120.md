---
id: VFBIZ-0120
title: Make Assistant Release v3 contract executable
status: done
mode: controlled
priority: P0
owner_team: architecture-integration
accountable_role: architect
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - contracts/ai/ai-release-manifest.schema.json
  - contracts/json-schema/ai-release-manifest.schema.json
  - contracts/fixtures/ai-release
  - tests/contract/ai-release
depends_on:
  - VFBIZ-0118
controlled_signals:
  - ai-release
  - public-contract
exclusive_resources:
  - ai-assistant-release-manifest
required_checks:
  - npm run contracts:lint
  - npm run governance:check
revision: 5
review_date: "2026-07-26"
updated_at: "2026-07-26T06:10:18.491Z"
---

# Outcome

Assistant Release v3 schema có positive/tamper fixtures thực thi được và không
còn reference pattern mâu thuẫn.

## Constraints

- Không nới opaque URI thành URL tùy ý.
- Fixture phải đi qua Draft 2020-12 validation với format checking.
- Semantic cross-field validation vẫn thuộc VFBIZ-0119.

## Done when

- `safe-release://` là approved opaque scheme hợp lệ.
- Positive fixture hợp lệ toàn schema; tamper/legacy fixture bị từ chối.
- Contract test thực sự load canonical Assistant Release schema.
- Contract và governance checks đạt.

## Checkpoint

- Exact next action: sửa opaque scheme regex và thêm deterministic fixtures.

## Evidence

- [x] `node tests/contract/ai-release/check-ai-release-schema.mjs` — passed at
  `d32a640`
- [x] `npm run contracts:lint` — passed at `d32a640`
- [x] `npm run governance:check` — passed at `d32a640`
