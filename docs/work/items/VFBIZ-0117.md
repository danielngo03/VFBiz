---
id: VFBIZ-0117
title: Canonicalize Assistant Release machine contract
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
  - contracts/ai/ai-release-manifest.schema.json
  - contracts/json-schema/ai-release-manifest.schema.json
depends_on:
  - VFBIZ-0104
controlled_signals:
  - ai-release
  - ai-safety
  - data-governance
exclusive_resources:
  - ai-release-manifest-contract
required_checks:
  - npm run contracts:lint
  - npm run governance:check
revision: 5
review_date: "2026-07-26"
updated_at: "2026-07-26T05:34:07.541Z"
---

# Outcome

Một canonical JSON Schema mô tả đúng immutable candidate, activation envelope,
approval/gate evidence, embedding generation, rollback và live controls; mọi
consumer cũ dùng generated compatibility artifact hoặc bị migrate có kiểm soát.

## Constraints

- `contracts/ai` là canonical AI contract.
- Không duy trì hai hand-edited schema có cùng ý nghĩa.
- Schema không chứa provider secret, raw prompt hoặc mutable model alias.
- Thay đổi breaking phải nâng contract version và có migration note.
- Data Governance review provenance/approval fields; Architecture Integration
  sở hữu cross-repository contract publication.

## Done when

- Canonical schema khớp domain objects của VFBIZ-0104 và chặn unknown fields.
- Legacy schema trong `contracts/json-schema` bị xóa hoặc generated
  deterministically; contract checker phát hiện drift.
- Positive/negative fixtures bao phủ semantic artifact role, replayed approval,
  profile/environment mismatch và rollback envelope.
- `contracts:lint` và governance contract scenarios đạt.

## Checkpoint

- Exact next action: inventory consumer của hai schema, chọn canonical v2 và
  thêm drift test trước khi xóa compatibility source.

## Evidence

- [x] `npm run contracts:lint` — canonical v2 và compatibility symlink đạt tại `858a837`
- [x] `npm run governance:check` — 114 work items và 61 routing scenarios đạt
