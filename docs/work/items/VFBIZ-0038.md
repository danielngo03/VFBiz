---
id: VFBIZ-0038
title: Allowlisted Vehicle Facts tool view
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
  - backend/api/test/integration/product
depends_on:
  - VFBIZ-0028
  - VFBIZ-0033
  - VFBIZ-0034
  - VFBIZ-0035
  - VFBIZ-0037
controlled_signals:
  - authorization
  - data-governance
  - ai-tool
  - vehicle-catalog
exclusive_resources: []
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 1
review_date: "2026-08-23"
---

# Outcome

Product application cung cấp một read-only Vehicle Facts view tối thiểu, có
provenance/freshness và an toàn để AI Gateway dùng; chatbot không đọc Prisma,
`extensionData` hoặc raw provider response.

## Constraints

- Static specification và dynamic price/promotion/inventory là operation riêng.
- Missing/stale/anomalous fact trả typed unavailable/conflict, không suy đoán.
- Garage self-reported không cấp verified ownership hoặc Vision capability.
- Tool view không chứa raw VIN, customer PII, internal approval payload hay
  business field ngoài allowlist.

## Done when

- Static view pin model/variant, market, release, typed unit, source revision,
  checksum, observed/effective/expiry time và availability.
- Dynamic commercial view đi qua anomaly gateway và session micro-cache policy.
- Authorization/object scope được kiểm tra trước khi lấy customer Garage view.
- Integration tests chứng minh stale/anomalous/unauthorized data không tới AI
  transport.

## Checkpoint

- Exact next action: định nghĩa application DTO/port từ contract đã duyệt; tool
  registration và model selection thuộc Conversation/AI lane sau.

## Evidence

- [ ] `npm run verify:api` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
