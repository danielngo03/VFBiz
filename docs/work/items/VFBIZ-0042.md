---
id: VFBIZ-0042
title: Thu hẹp API runtime về Account, Customer và Product foundation
status: review
mode: controlled
priority: P0
owner_team: architecture-integration
accountable_role: architect
primary_workspace: api
affected_workspaces:
  - api
  - root
allowed_paths:
  - backend/api/AGENTS.md
  - backend/api/README.md
  - backend/api/src/app.module.ts
  - backend/api/src/platform/config
  - backend/api/test/contract
  - backend/api/test/e2e/engagement
  - contracts/openapi
  - backend/api/docs
  - docs/work/items
depends_on: []
controlled_signals:
  - architecture
  - public-contract
exclusive_resources:
  - public-contract
required_checks:
  - npm run verify:api
  - npm run contracts:lint
  - npm run governance:check
revision: 4
review_date: "2026-07-23"
updated_at: "2026-07-23T11:39:27.077Z"
---

# Outcome

API localhost chỉ compose và công bố các capability nền tảng đã có runtime
evidence: Authentication, Customer, Garage, Vehicle Catalog và health. Chatbot,
Trip Planner và Operations chưa sẵn sàng không được yêu cầu secret hoặc xuất
hiện trong public OpenAPI.

## Constraints

- Không xóa source code thử nghiệm của Engagement/Mobility trong work item này.
- Không thay đổi business logic Account, Customer hoặc Product.
- Capability tương lai chỉ được bật lại bằng work item, reviewed contract và
  runtime evidence riêng.

## Done when

- `AppModule` không compose Engagement/Mobility.
- API cơ bản khởi động không cần Google Maps, Trip hoặc AI configuration.
- Runtime và reviewed OpenAPI không công bố Chat/Trip/Operations.
- Contract, API và governance gates đạt.

## Checkpoint

- Exact next action: Architect review narrowed runtime/contract. Database
  foundation tiếp tục ở VFBIZ-0032/0033 sau các review gate tương ứng.

## Audit findings

- PostgreSQL localhost nhận kết nối nhưng ban đầu thiếu role/database `vfbiz`;
  role và database local rỗng đã được tạo theo `.env`.
- Native PostgreSQL hiện là 14.20 và không có PostGIS. Migration bị chặn đúng
  tại prerequisite, sau đó database mới tạo được reset về rỗng; không có dữ
  liệu người dùng bị xóa.
- OIDC callback chưa materialize session projection; cần work item Access riêng
  thay vì giấu trong contract cleanup.
- DSAR mới tạo request; target execution thuộc VFBIZ-0032.
- Vehicle Catalog write/approval/atomic activation thuộc VFBIZ-0033 và đang
  chờ Source Revision review.
- Price, promotion và inventory còn thiếu governed projection đầy đủ; thuộc
  VFBIZ-0034 sau khi Catalog activation hoàn tất.

## Evidence

- [x] `npm run verify:api` — 29 suites/135 unit tests, 8 suites/47 E2E tests,
  lint/typecheck/Prisma/build đạt ngày 23/07/2026.
- [x] `npm run contracts:lint` — Public/Internal OpenAPI hợp lệ, không warning;
  runtime schema check đạt ngày 23/07/2026.
- [x] `npm run governance:check` — 39 WorkItemV2 và 55 provider-neutral context
  scenarios đạt ngày 23/07/2026.

### ready — 2026-07-23T11:36:05.249Z

User đã khóa scope nền tảng Account/Customer/Product; Chat/Trip/Operations chưa được public.

### active — 2026-07-23T11:36:05.538Z

Thu hẹp composition root, environment contract và OpenAPI về capability có runtime evidence.

### review — 2026-07-23T11:39:27.077Z

Composition root, environment contract và OpenAPI đã thu hẹp về capability nền tảng có runtime evidence; chờ Architect review.
