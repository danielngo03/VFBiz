---
id: VFBIZ-0089
title: Harden AI execution contract after independent review
status: done
mode: controlled
priority: P0
owner_team: architecture-integration
accountable_role: architect
primary_workspace: root
affected_workspaces:
  - root
  - ai
allowed_paths:
  - contracts/ai/ai-execution-assertion.schema.json
  - contracts/ai/canonical-request-hash-vectors.json
  - contracts/openapi/internal-v1.yaml
depends_on:
  - VFBIZ-0019
controlled_signals:
  - public-contract
  - ai-assistant
  - authorization
  - pii
exclusive_resources:
  - public-contract
required_checks:
  - npm run contracts:lint
  - npm run governance:check
revision: 5
review_date: "2026-08-23"
updated_at: "2026-07-24T18:52:18.322Z"
---

# Outcome

AI Execution Assertion và Internal AI OpenAPI khóa chặt profile/tool boundary,
failure contract và canonical request binding để NestJS/FastAPI triển khai cùng
một giao thức fail-closed.

## Constraints

- Chỉ thay đổi contract; không triển khai runtime hoặc business graph.
- Public profile không được cấp customer-scoped tool.
- Thay đổi phải backward-compatible với candidate protocol chưa phát hành.
- Contract và OpenAPI giữ exclusive lease trong toàn bộ lần sửa.

## Done when

- Public authorization chỉ cho phép `search_public_knowledge`.
- Internal problem schema mô tả đủ 413/422/500, retryability và RFC Problem
  Details fields thực tế.
- Cancellation contract không hứa acknowledgement trước khi runtime chấp nhận.
- Canonical hash rules có mô tả rõ và fixture liên runtime có thể triển khai ở
  lane NestJS tiếp theo.
- Contract lint và governance gate đạt.

## Checkpoint

- Exact next action: acquire `public-contract` lease, update the two shared
  contracts, then hand the frozen result to VFBIZ-0020 runtime fix cycle.

## Evidence

- [x] `npm run contracts:lint` — PASS; five OpenAPI documents, six runtime
  schemas and eight isolated candidate operations validate without warnings.
- [x] `npm run governance:check` — PASS; 86 work items and 61 context scenarios
  remain valid.

### Independent review

- Cycle 1 found response tool membership, canonical hashing and cancellation
  status gaps; commits `f603948` and `4cf95d0` resolved them.
- Cycle 2 found JavaScript unsafe-integer drift; commit `f33565b` bounded every
  signed integer and added boundary/rejection vectors. No P0 remains.
