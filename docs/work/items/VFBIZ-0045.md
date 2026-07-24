---
id: VFBIZ-0045
title: Account, Customer và Product foundation readiness audit
status: review
mode: discovery
priority: P0
owner_team: api-foundation
accountable_role: architect
primary_workspace: api
affected_workspaces:
  - api
  - infra
allowed_paths:
  - docs/work/items
  - WORK.md
depends_on: []
controlled_signals:
  - architecture
  - data-governance
  - authentication
  - customer-data
  - vehicle-catalog
exclusive_resources: []
required_checks:
  - npm run governance:check
revision: 9
review_date: "2026-08-24"
updated_at: "2026-07-24T10:00:00.000+07:00"
---

# Outcome

Có một readiness matrix dựa trên schema, route, runtime composition, migration
và observed tests để phân biệt foundation đã đạt, phần đang review và blocker
chưa được phép gọi là enterprise-ready.

## Constraints

- Không mở Chatbot, Trip Planner, commerce hoặc ownership runtime trong audit.
- Không coi model/table tồn tại là capability đã hoàn thiện.
- Không tạo VinFast fact, customer PII, provider contract hoặc approval giả.
- PostgreSQL 14 chứa database ngoài phạm vi VFBiz; chỉ retirement database
  `vfbiz` trống sau backup, không nâng cấp hoặc dừng database VinUni.

## Done when

- Runtime chỉ compose `access`, `customer` và `product`.
- Database VFBiz chính thức chạy PostgreSQL 17/PostGIS và không còn duplicate
  database VFBiz trên PostgreSQL 14.
- Mỗi foundation capability có state `ready`, `review`, `missing` hoặc
  `blocked-by-external-authority`.
- Mỗi gap P0 có đúng một work item, dependency và accountable human role.
- Module/folder boundaries và public route inventory được architecture test.

## Checkpoint

### Readiness matrix

| Capability | State | Evidence hoặc gap |
| --- | --- | --- |
| PostgreSQL/PostGIS local | `review` | VFBIZ-0043: PostgreSQL 17.10, PostGIS 3.6.4, 14 migrations và native replay đạt |
| OIDC/JWKS/resource authorization | `review` | VFBIZ-0047 real-provider login/callback/refresh/logout đạt; còn Security Owner và SMTP/MFA integration acceptance |
| Session list/revoke/reconcile | `ready` | VFBIZ-0029 done; callback/refresh materialize verified session qua VFBIZ-0044 |
| OIDC session materialization | `ready` | VFBIZ-0044 done; verified temporal claims + `sid`, suspend/revoke fail closed |
| Customer Profile/OCC | `ready` | VFBIZ-0014 + VFBIZ-0050; suspend guard, OCC, audit/outbox và PostgreSQL integration đạt |
| Consent ledger | `review` | Append-only ordering, approved ConsentPolicy registry, audit/outbox và idempotency đã code-complete; còn Privacy Owner acceptance |
| DSAR request intake | `review` | VFBIZ-0032 snapshot target/event/audit/outbox và subject-scoped status; không tuyên bố đã export/delete |
| DSAR execution adapters | `missing` | VFBIZ-0049 cần retention/deadline/recent-auth/legal-hold authority |
| Customer Garage self-reported | `ready` | VFBIZ-0050: subject scope, OCC, primary invariant, idempotency, suspend guard và atomic audit/outbox |
| Verified vehicle/VIN | `blocked-by-external-authority` | VFBIZ-0036 cần DMS/CRM contract, Data/Privacy Owner |
| Catalog read model | `review` | Active release reader + source/freshness/provenance gate đã có |
| Catalog release write/approve/rollback | `review` | VFBIZ-0052 technical enabler đạt OCC, atomic activation/rollback và audit/outbox; workforce authority/Data Owner acceptance còn ở VFBIZ-0033/0039 |
| Price/promotion/inventory | `review` | VFBIZ-0053 có governed schema, anomaly gate, synthetic seed và public price/promotion read; production source/provider contract còn ở VFBIZ-0034 |
| Public contract/SDK parity | `review` | Toàn bộ public operation inventory được đối chiếu; Account VFBIZ-0030 và independent Catalog review VFBIZ-0037 còn mở |
| Readiness health | `review` | VFBIZ-0046: database probe, 200/503 E2E và reviewed OpenAPI đạt |
| Audit/outbox/idempotency platform | `partial` | Profile, Consent, DSAR và Garage đã atomic; Catalog activation, external adapters và future contexts chưa mở |
| Seed/reference data | `review` | VFBIZ-0051/0053 có local-only synthetic Catalog + commercial release, source candidate registry và download/approval gate; dữ liệu VinFast thật vẫn chờ Data/Legal Owner |

### Structure verdict

- NestJS modular monolith và các layer
  `domain/application/infrastructure/presentation` ở ba active context là đúng.
- `AppModule` chỉ compose `access`, `customer`, `product`; Chat/Trip không public.
- `engagement`, `mobility` và physical ownership schema là historical/future
  boundary, không phải active capability.
- Không tạo thêm top-level module theo từng endpoint hoặc provider.
- Prisma record không được trả trực tiếp; controller DTO và repository port đã
  tách.

### Sequencing bắt buộc

1. Human Security/Privacy/Data/Architecture owners accept hoặc trả finding mới
   cho VFBIZ-0030/0031/0032/0039/0042/0043.
2. VFBIZ-0033: mở workforce release operations sau provenance/role acceptance;
   state machine và persistence đã code-complete trong VFBIZ-0052.
3. VFBIZ-0034: production commercial ingestion chỉ sau provider/source
   contract; projection/read foundation đã code-complete trong VFBIZ-0053.
4. VFBIZ-0037: reviewed Catalog contract + reproducible SDK.
5. VFBIZ-0049: DSAR execution sau retention/deadline/recent-auth/legal-hold
   policy.
6. Chỉ sau các gate trên mới mở read-only Vehicle Facts cho AI.

Exact next action: review VFBIZ-0046/0047/0048; các controlled work item còn
lại chỉ chuyển `ready` khi dependency/human gate đạt.

## Evidence

- [x] Runtime module, Prisma schema, migration constraints, public route và
  active work-item inventory được audit ngày 2026-07-23.
- [x] PostgreSQL 14 duplicate `vfbiz` không có user table; custom dump + role
  backup có SHA-256 nằm ngoài Git trước khi retirement.
- [x] PostgreSQL 17 `vfbiz` có 14 completed Prisma migration và PostGIS 3.6.4.
- [x] Runtime database có 46 user/application table ngoài
  `spatial_ref_sys`, geography `charging_station.location` kiểu Point/SRID
  4326 và GiST index; không có business row chưa được phê duyệt.
- [x] Public API inventory hiện có 24 operation cho health, OIDC, customer,
  consent, session, data request, garage, catalog và commercial read model; route
  versioned chỉ phục vụ dưới `/api/v1`, OIDC giữ `/auth`.
- [x] `npm run verify:api` — 32 suite/153 unit tests, 8 suite/54 E2E tests,
  lint/typecheck/Prisma/build đạt ngày 2026-07-24.
- [x] `npm run contracts:lint` và `npm run verify:apps` đạt; OpenAPI không
  warning, Customer Portal 3 test và Operations Admin 2 test đạt.
- [x] Các workspace gates đạt ngày 2026-07-24: governance, API, apps, AI
  (25 test, Ruff/Pyright/Alembic) và Drupal
  (Composer/PHPCS/PHPStan/PHPUnit/config status).
- [x] `npm run governance:check` — 47 WorkItemV2, instruction/role/skill/adapters
  và 55 provider-neutral scenarios đạt.
