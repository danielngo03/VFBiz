---
id: VFBIZ-0036
title: Verified Vehicle Asset và customer association
status: proposed
mode: discovery
priority: P1
owner_team: product-management
accountable_role: data-owner
primary_workspace: root
affected_workspaces:
  - root
  - api
allowed_paths:
  - docs/work/plans
depends_on:
  - VFBIZ-0035
controlled_signals:
  - vehicle-ownership
  - pii
exclusive_resources: []
required_checks:
  - npm run governance:check
revision: 1
review_date: "2026-08-23"
---

# Outcome

Tạo decision-ready design cho Vehicle Asset, tokenized VIN, association và
verification case dựa trên contract DMS/CRM thật; chưa tạo runtime schema.

## Constraints

- Thiếu source owner, API contract hoặc verification SLA thì không implement.
- Association phải phân biệt owner, authorized driver và fleet user.
- Evidence, validity, source/freshness và revoke lifecycle bắt buộc.
- Vision chỉ mở khi verified association policy đã được phê duyệt.

## Done when

- System-of-record, trust boundary, identifier/tokenization và lifecycle rõ.
- Threat/privacy/data review có owner và open question cụ thể.
- ADR/work item implementation chỉ được tạo sau provider evidence.
- Không có schema/code placeholder tạo cảm giác capability đã tồn tại.

## Checkpoint

- Exact next action: thu thập DMS/CRM contract và Data/Privacy decision; nếu
  chưa có thì giữ discovery, không hỏi lại câu đã có trong docs.

## Evidence

- [ ] `npm run governance:check` — add evidence reference
