---
id: VFBIZ-0053
title: Commercial data projection foundation
status: review
mode: controlled
priority: P0
owner_team: customer-product
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/product
  - backend/api/prisma/models/product.prisma
  - backend/api/prisma/models/platform.prisma
  - backend/api/prisma/migrations
  - backend/api/prisma/seed
  - backend/api/test/integration/product
  - backend/api/docs/vehicle-catalog-and-garage.md
  - contracts/openapi/public-v1.yaml
  - packages/api-client
  - backend/api/test/contract
  - docs/work/items/VFBIZ-0034.md
  - docs/work/items/VFBIZ-0053.md
  - WORK.md
depends_on:
  - VFBIZ-0052
controlled_signals:
  - data-governance
  - migration
  - vehicle-catalog
  - public-contract
exclusive_resources:
  - database-migration
  - public-contract
required_checks:
  - npm run verify:api
  - npm run test:migrations --workspace @vfbiz/api
  - npm run governance:check
revision: 2
review_date: "2026-08-24"
updated_at: "2026-07-24T14:20:00.000+07:00"
---

# Outcome

Giá, promotion và inventory có schema/version/provenance/validity rõ, không còn
dùng `PriceProjection` tối giản hoặc dữ liệu động không có anomaly gate.

## Constraints

- Chỉ seed synthetic fixture; không nhập giá/promotion VinFast khi Source
  Candidate chưa được Data/Legal Owner duyệt.
- Commercial release tách khỏi Catalog release nhưng chỉ tham chiếu stable
  model/variant đã tồn tại.
- Inventory là observation có expiry, không phải lời hứa tồn kho/giao xe.
- Chưa mở Operations write API trước khi workforce role matrix được duyệt.

## Done when

- Database có commercial release, price offer, promotion, inventory observation
  và anomaly record với constraint/index phù hợp.
- Domain policy fail-closed với source stale, validity sai, amount bất thường,
  promotion conflict hoặc blocking anomaly.
- Local synthetic seed idempotent và public read path chỉ trả active/fresh facts.
- Migration replay, PostgreSQL integration và API gate đạt.

## Checkpoint

- Code complete: governed commercial release, price, promotion, inventory và
  anomaly schema; public read API chỉ trả active/fresh/anomaly-free facts.
- Local seed có hai synthetic price và một synthetic promotion, idempotent;
  không có VinFast fact hoặc production ingestion.
- Inventory schema đã sẵn sàng nhưng không seed/expose trước provider contract.
- Exact next action: independent Product/Data review; Business Owner và
  external adapter contract vẫn thuộc VFBIZ-0034.

## Evidence

- [x] `npm run verify:api` — lint/typecheck, 35 suites/167 tests, 8 E2E
  suites/55 tests, Prisma validate và build đạt ngày 24/07/2026.
- [x] `npm run test:migrations --workspace @vfbiz/api` — 14 migrations, schema
  drift rỗng, 5 PostgreSQL suites/16 tests và legacy backfill đạt.
- [x] `npm run contracts:lint` + SDK generation — không warning.
- [x] `npm run governance:check` — 50 WorkItemV2, current generated index và
  55 provider-neutral context scenarios đạt.
- [x] Local smoke — PostgreSQL 17/PostGIS 3.6.4 ready; API trả một synthetic
  commercial release với hai price offer và một promotion, mỗi fact có
  market/source/freshness/validity.
