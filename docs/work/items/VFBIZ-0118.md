---
id: VFBIZ-0118
title: Strengthen Assistant Release rollback contract
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
depends_on:
  - VFBIZ-0117
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
updated_at: "2026-07-26T05:53:09.865Z"
---

# Outcome

Canonical Assistant Release contract định danh rollback bằng exact prior
activation và quy định rõ activation envelope, history, idempotency và outbox.

## Constraints

- Rollback pin activation ID và activation-envelope digest, không chỉ candidate.
- Current state được suy ra từ append-only history và active pointer; activation
  envelope không chứa mutable lifecycle authority.
- Không tạo representation riêng ngoài canonical schema.
- Contract không chứa provider credential hoặc production approval giả.

## Done when

- Rollback target không thể là current activation hoặc tạo lineage cycle.
- Schema pin profile, environment, effective window, live-control evidence,
  promotion evidence và exact rollback activation.
- History/outbox/idempotency contract đủ cho transactional persistence.
- Compatibility symlink tiếp tục trỏ canonical schema.
- Contract và governance checks đạt.

## Checkpoint

- Exact next action: đồng bộ domain object ở VFBIZ-0119 sau khi schema được review.

## Evidence

- [x] `npm run contracts:lint` — passed at `c9a4d4c`
- [x] `npm run governance:check` — passed at `c9a4d4c`
- [x] Independent architecture review — P0 digest/lifecycle finding fixed,
  evidence `34762b3c79c24b576e2f4bd99d40e402133efbd415d6f6c660ebc4492b56d9f7`
