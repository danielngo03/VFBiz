---
id: VFBIZ-0015
title: Vehicle Catalog release và structured data foundation
status: done
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
  - backend/api/prisma/migrations
  - backend/api/test
  - contracts/openapi
  - packages/api-client
  - backend/api/docs
  - docs/work
  - WORK.md
depends_on:
  - VFBIZ-0012
controlled_signals:
  - vehicle-catalog
  - data-governance
  - schema
  - migration
  - public-contract
exclusive_resources:
  - database-migration
  - public-contract
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 5
review_date: "2026-08-23"
updated_at: "2026-07-23T06:06:05.136Z"
---

# Outcome

API phát hành Vehicle Catalog có model/variant identity ổn định, structured
specification được version hóa và chỉ expose một approved release nguyên tử có
source/freshness rõ ràng.

## Constraints

- Drupal sở hữu marketing copy, SEO, translation và media; API không sao chép
  các field editorial.
- Không dùng promotion/price/vehicle fact thiếu source revision, effective
  window hoặc approval.
- `specifications: Json` không được tiếp tục là schema business không kiểm soát.
- Staging dùng fixture synthetic/versioned; chưa giả lập PIM/ERP production.

## Done when

- Model và variant có immutable stable identity; slug/code có lifecycle rõ.
- Catalog release pin toàn bộ revision; database chỉ cho một active release mỗi
  market và public read luôn lấy model/variant cùng một release.
- Structured fields dùng unit chuẩn, nullable semantics và validation rõ ràng;
  extension data nếu có phải versioned bằng schema.
- List/detail endpoint trả source revision, effective time, freshness và trạng
  thái unavailable khi chưa có approved release.
- Price/promotion không lọt vào response từ dữ liệu anomaly hoặc stale.
- Contract, SDK, migration, fixture và tests đạt.

## Checkpoint

- Stable identity, immutable revision, active-release read model và public
  contract đã hoàn tất; exact next action là đóng work item và mở Garage.

## Evidence

- [x] `npm run verify:api` — lint/typecheck, 48 unit/architecture tests,
  18 E2E tests, Prisma validation và Nest build đạt ngày 2026-07-23.
- [x] `npm run governance:check` — 49 durable docs, 13 work item,
  37 routing scenario và nested instruction budget đạt ngày 2026-07-23.

Evidence bổ sung:

- Migration replay đạt trên clean DB và legacy fixture với 4 migration, zero
  schema drift; legacy mutable/JSON fields được chuyển vào immutable revision.
- OpenAPI lint và generated API client typecheck đạt.

Residual scope: ingest/approve/activate command cho Operations Admin là controlled
write workflow riêng. Baseline public reader chỉ expose release đã `active` và
SourceRevision `approved`/fresh, nên dữ liệu legacy `draft` không bị public.
