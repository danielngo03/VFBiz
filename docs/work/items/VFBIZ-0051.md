---
id: VFBIZ-0051
title: Product data seed và source candidate foundation
status: review
mode: controlled
priority: P0
owner_team: customer-product
accountable_role: data-owner
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/prisma/seed
  - backend/api/src/modules/product
  - backend/api/test/unit/product
  - backend/api/package.json
  - package-lock.json
  - backend/api/.env.example
  - backend/api/docs/vehicle-catalog-and-garage.md
  - docs/work/items/VFBIZ-0051.md
  - WORK.md
depends_on: []
controlled_signals:
  - data-governance
  - vehicle-catalog
exclusive_resources:
  - root-lockfile
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 2
review_date: "2026-08-24"
updated_at: "2026-07-24T12:00:00.000+07:00"
---

# Outcome

Local database có seed deterministic để kiểm thử Catalog mà không giả làm dữ
liệu VinFast đã được phê duyệt; nguồn chính thức được đăng ký ở trạng thái
candidate và bị chặn trước download/import khi thiếu quyền, checksum hoặc
approval evidence.

## Constraints

- Seed synthetic chỉ chạy khi được bật rõ ràng và chỉ được trỏ tới PostgreSQL
  localhost.
- Không dùng nội dung Website/PDF cho AI training.
- Candidate source không được tạo `ACTIVE` release.
- Source public không đồng nghĩa đã có quyền ingest hoặc phát hành.
- Giá và promotion phải giữ document code, hiệu lực, market, tax context và
  source revision; không ép thành một trường `currentPrice`.

## Done when

- `prisma/seed` có cấu trúc rõ, local guard, manifest và idempotent transaction.
- Có source candidate registry cho tài liệu chính thức tháng 07/2026 nhưng
  chưa download/import khi rights state chưa approved.
- Validator từ chối missing URL, invalid market/date, AI training purpose và
  approved source thiếu checksum/evidence.
- Synthetic release có provenance rõ, không chứa nhãn hiệu/thông số/giá
  VinFast và có thể reset/reseed deterministic.
- Unit test và API gate đạt.

## Checkpoint

Code-complete. Exact next action: Data Owner xác nhận candidate registry chỉ là
metadata tham chiếu và synthetic fixture không được dùng ngoài local/test; sau
đó cho phép đóng work item hoặc trả finding mới.

## Evidence

- [x] `seed:validate` từ chối write và kiểm registry thành công.
- [x] `seed:local` chạy idempotent hai lần trên PostgreSQL 17/PostGIS local.
- [x] Database có 1 model, 2 variant revision và 10 fact provenance binding cho
  release `local-synthetic-v1`.
- [x] Live Catalog API trả release synthetic cùng source/freshness, không có
  dữ liệu VinFast giả.
- [x] API lint, typecheck, 159 unit/integration test, 54 E2E, Prisma validate và
  build đạt ngày 2026-07-24.
- [x] `npm run governance:check` — 52 documents, 48 work items và 55
  provider-neutral scenarios đạt.
- [x] Migration clean replay/legacy backfill và 13 migration tests đạt.
