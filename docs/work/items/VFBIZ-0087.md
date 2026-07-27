---
id: VFBIZ-0087
title: Conversation contract validation gate
status: done
mode: controlled
priority: P0
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - tools/check-runtime-contracts.mjs
depends_on: []
controlled_signals:
  - public-contract
  - ai-assistant
exclusive_resources: []
required_checks:
  - npm run contracts:lint
  - npm run verify:governance
revision: 5
review_date: "2026-08-25"
updated_at: "2026-07-24T18:23:32.644Z"
---

# Outcome

Deterministic contract checker compile toàn bộ Conversation Turn/Event/Assertion
JSON Schema và bảo vệ vocabulary public ổn định mà không phụ thuộc provider.

## Constraints

- Chỉ sửa deterministic checker; không sửa business contract hoặc runtime code.
- Không thêm dependency, network call hoặc generated baseline dễ drift.
- Gate phải kiểm schema bằng AJV strict mode và xác nhận operation ID bắt buộc
  vẫn tồn tại trong generated public client.

## Done when

- Ba Conversation JSON Schema compile bằng AJV 2020 strict mode.
- Checker xác nhận các public operation ID create/get/close session, enqueue/list
  message, stream events, cancel và handoff tồn tại.
- Contract lỗi hoặc operation bị xóa làm command exit khác 0.
- `contracts:lint` và governance gate đạt.

## Checkpoint

- Coordination `coord-ca1e6fe1-dc4e-4196-b661-1a48f4a270bf` yêu cầu Agent Platform
  triển khai checker trên contract đã được Architecture & Integration khóa.
- Exact next action: cập nhật checker, chạy negative fixture in-memory và trả
  evidence về coordination request.

## Evidence

- [x] `npm run contracts:lint` — PASS; AJV compiled 6 schemas and verified 8
  required Conversation operation IDs.
- [x] `npm run verify:governance` — PASS; adapters, agent/work control, docs,
  reports, authorization, work schemas, routing scenarios and contract gates.
- [x] `node tools/check-runtime-contracts.mjs --self-test` — PASS; missing
  operation IDs and an unknown strict-schema keyword were rejected.

### review — 2026-07-24T18:23:32.360Z

Implementation and deterministic negative self-test complete; contracts and governance gates passed.

### done — 2026-07-24T18:23:32.644Z

Accepted by observed deterministic evidence; coordination coord-ca1e6fe1-dc4e-4196-b661-1a48f4a270bf responded and closed.
