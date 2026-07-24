---
id: VFBIZ-0039
title: Governed Source Revision và fact provenance
status: review
mode: controlled
priority: P0
owner_team: api-foundation
accountable_role: data-owner
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/platform
  - backend/api/src/modules/product
  - backend/api/prisma/models/platform.prisma
  - backend/api/prisma/models/product.prisma
  - backend/api/prisma/migrations
  - backend/api/docs/data-model.md
  - backend/api/docs/vehicle-catalog-and-garage.md
  - backend/api/test/integration/platform
  - backend/api/test/integration/product
depends_on:
  - VFBIZ-0015
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
revision: 9
review_date: "2026-08-23"
updated_at: "2026-07-23T17:19:44.162Z"
---

# Outcome

Mọi operational projection có Source Revision typed, không thể activate với
owner/provenance/license/classification/approval placeholder; fact group có thể
pin đúng nguồn thay vì mượn một source chung cho toàn release.

## Constraints

- Source record là governance evidence, không chứa binary/source payload.
- Requester không tự approve nguồn hoặc release dùng nguồn đó.
- Classification, approval state và permitted purpose dùng vocabulary typed.
- Không sửa migration đã áp dụng; dùng expand/backfill/contract.

## Done when

- Placeholder `unassigned`, `UNVERIFIED` và approval string tùy ý bị fail-closed.
- Source pin external revision/checksum, observed/ingested/effective/expiry time,
  rights/purpose và approval evidence.
- Fact provenance binding hỗ trợ entity/fact group mà không tạo EAV tùy ý.
- PostgreSQL integration và clean/legacy migration replay đạt.

## Checkpoint

- Exact next action: Data Owner review fact-level provenance coverage,
  membership và PUBLIC classification; không activate Catalog release trước
  quyết định này.

## Evidence

- [x] `npm run verify:api` — lint/typecheck/Prisma/build đạt; 32 unit suites với
  153 tests và 8 E2E suites với 54 tests đạt ngày 24/07/2026.
- [x] `npm run test:migrations --workspace @vfbiz/api` — clean/legacy replay
  đạt với 11 migration; 3 PostgreSQL migration/integration suites với 13 tests
  đạt ngày 24/07/2026.
- [x] `npm run governance:check` — instruction, role, skill, work schema và 55
  provider-neutral context scenarios đạt ngày 24/07/2026.

### ready — 2026-07-23T11:14:39.654Z

Consumer inventory hoàn tất: Vehicle Catalog, Price, Energy, Charging Station/Tariff đang dùng SourceRevision; placeholder governance phải fail closed.

### active — 2026-07-23T11:14:39.951Z

Triển khai typed source governance và fact-group provenance trước Catalog activation.

### review — 2026-07-23T11:20:44.520Z

Typed SourceRevision, fact-group provenance, migration và PostgreSQL evidence đã hoàn tất; chờ Data Owner review trước khi mở VFBIZ-0033.

### blocked — 2026-07-23T16:48:42.820Z

Review phát hiện public reader chưa kiểm fact-level provenance/membership và publication classification; mở corrective pass fail-closed.

### active — 2026-07-23T16:48:43.101Z

Triển khai corrective publication policy và negative tests; không activate release hoặc dữ liệu mới.

### review — 2026-07-23T17:19:44.162Z

Corrective reader đã fail closed theo fact-level provenance, release membership và PUBLIC classification; negative tests và gates đạt. Chờ Data Owner acceptance.
