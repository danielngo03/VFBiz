---
id: VFBIZ-0033
title: Vehicle Catalog release operations và atomic activation
status: proposed
mode: controlled
priority: P0
owner_team: customer-product
accountable_role: data-owner
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/product
  - backend/api/prisma/models/product.prisma
  - backend/api/test/integration/product
  - backend/api/test/e2e/product
depends_on:
  - VFBIZ-0015
  - VFBIZ-0039
  - VFBIZ-0052
controlled_signals:
  - data-governance
  - migration
  - vehicle-catalog
exclusive_resources:
  - database-migration
required_checks:
  - npm run verify:api
  - npm run test:migrations --workspace @vfbiz/api
  - npm run governance:check
revision: 3
review_date: "2026-08-23"
---

# Outcome

Vehicle Catalog chỉ public một release có source/provenance/schema/checksum và
approval evidence hợp lệ; activation, rollback và supersede là atomic.

## Constraints

- Requester không được tự approve release của chính mình.
- `UNVERIFIED`, `unassigned` hoặc source/provenance mặc định không được public.
- Specification dùng controlled vocabulary, unit rõ và versioned schema.
- Provenance được pin theo entity/fact group; không coi một source của release
  là bằng chứng cho mọi specification.
- Không trộn price, promotion, inventory hoặc ownership vào catalog release.

## Done when

- Candidate/approved/active/superseded/rolled-back lifecycle có invariant rõ.
- Release manifest pin membership, schema, source/checksum và approval evidence
  theo fact group.
- Reader defense-in-depth kiểm source, effective window và active pointer.
- Atomic activation và rollback không tạo hai active release cùng market.
- PostgreSQL integration, reconciliation và migration replay đạt.

## Checkpoint

- VFBIZ-0052 đã hoàn tất technical enabler và đang ở `review`: database state
  invariant, release eligibility, OCC, atomic activation/rollback và
  audit/outbox đã có test.
- VFBIZ-0054 đã bổ sung workforce API với realm, role, MFA, OCC và
  separation-of-duties; public OpenAPI không expose command quản trị.
- Work item này vẫn `proposed` vì còn cần Data Owner chấp nhận provenance,
  production ingestion/reconciliation contract và release runbook.
- Exact next action: Data Owner chấp nhận source boundary và owner/provider của
  production ingestion; không tạo adapter noop hoặc crawl dữ liệu chưa có quyền.

## Evidence

- [ ] `npm run verify:api` — add evidence reference
- [ ] `npm run test:migrations --workspace @vfbiz/api` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
