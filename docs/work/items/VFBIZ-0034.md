---
id: VFBIZ-0034
title: Price, promotion và inventory governed projections
status: proposed
mode: controlled
priority: P0
owner_team: customer-product
accountable_role: business-owner
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/product
  - backend/api/prisma/models/product.prisma
  - backend/api/test/integration/product
depends_on:
  - VFBIZ-0033
  - VFBIZ-0053
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

Giá, promotion và inventory là projection có hiệu lực/freshness riêng để
chatbot gọi bằng read-only tool; chúng không đi vào RAG hoặc model memory.

## Constraints

- Giá pin currency, amount minor, market, price type, tax context, channel,
  eligibility và effective window.
- Promotion pin rule/benefit, stacking policy và approval revision.
- Inventory là observation theo location/variant với TTL ngắn, không hứa giao
  xe khi source stale.
- Anomaly gateway chặn business conflict trước khi fact tới AI.

## Done when

- `PriceOffer`, `Promotion` và `InventoryObservation` có projection/schema cùng
  source-of-record adapter port tách khỏi catalog core.
- Missing/stale/anomalous fact trả typed unavailable/conflict, không suy đoán.
- Micro-TTL session cache bind subject/capability + operation + fact revision,
  không biến thành global semantic cache.
- Tests bao phủ giá bất thường, promotion conflict và inventory stale.

## Checkpoint

- VFBIZ-0053 triển khai schema/read foundation bằng synthetic fixture, không
  kích hoạt dữ liệu VinFast thật.
- VFBIZ-0054 đã materialize commercial approve/activate/rollback với role
  operator/reviewer tách biệt, MFA, source/fact/anomaly gate, audit và outbox.
- Work item này vẫn cần Business/Data Owner phê duyệt source, PIM/ERP/DMS
  contract, inventory semantics và micro-TTL consumer trước production.
- Exact next action: chốt provider/owner/SLA và reconciliation contract; thiếu
  authority thì giữ synthetic foundation, không giả lập dữ liệu thật.

## Evidence

- [ ] `npm run verify:api` — add evidence reference
- [ ] `npm run test:migrations --workspace @vfbiz/api` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
