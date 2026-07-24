---
id: plan-account-vehicle-enterprise-hardening
title: ExecPlan hardening Account và Vehicle foundation
status: active
owner_role: engineering-lead
scope: cross-system
when_to_read:
  - VFBIZ-0027
  - VFBIZ-0028
  - VFBIZ-0029
  - VFBIZ-0030
  - VFBIZ-0031
  - VFBIZ-0032
  - VFBIZ-0033
  - VFBIZ-0034
  - VFBIZ-0035
  - VFBIZ-0036
  - VFBIZ-0037
  - VFBIZ-0038
  - VFBIZ-0039
tags:
  - account
  - authorization
  - vehicle
  - data-governance
revision: 2
review_date: 2026-08-23
supersedes: []
---

# Purpose

Đóng các gap được audit sau staging foundation trước khi mở authenticated
Customer Chatbot, Garage tool, dynamic commercial fact hoặc Vision.

## Progress

- [x] VFBIZ-0027: OIDC scope policy/guard.
- [ ] VFBIZ-0028: Account/Consent/Garage scope enforcement.
- [ ] VFBIZ-0029: Access session projection và revoke/reconciliation.
- [ ] VFBIZ-0030: reviewed OpenAPI/runtime contract parity.
- [ ] VFBIZ-0031: consent atomicity và PostgreSQL integration tests.
- [ ] VFBIZ-0032: DSAR target orchestration.
- [ ] VFBIZ-0033: Vehicle Catalog governed release/activation.
- [ ] VFBIZ-0034: dynamic price/promotion/inventory projections.
- [ ] VFBIZ-0035: quarantine legacy ownership schema.
- [ ] VFBIZ-0036: verified Vehicle Asset discovery khi có DMS/CRM contract.
- [ ] VFBIZ-0037: Vehicle Catalog runtime/OpenAPI/SDK parity.
- [ ] VFBIZ-0038: allowlisted Vehicle Facts tool view.
- [ ] VFBIZ-0039: typed Source Revision và fact provenance.

## Dependency và concurrency

```text
0013 -> 0027 -> 0028 -> 0030
              \-> 0029 -/
0014 -> 0031
0014 + 0029 -> 0032
0015 -> 0039 -> 0033 -> 0034 -> 0037 -> 0038
0016 -> 0035 -> 0036 (discovery, provider-dependent)
```

Hai writer chỉ chạy song song khi path disjoint. Contract, migration và shared
registry cần exclusive lease. Security/Privacy/Data/Architecture reviewer chạy
read-only; không biến review thành writer thứ hai.

## Release gates cho Chatbot

- Public chatbot có thể phát triển graph/knowledge bằng synthetic fixture.
- `authenticated_customer` không mở trước VFBIZ-0027/0028/0029/0031/0032.
- Vehicle catalog tool không mở trước VFBIZ-0033.
- Price/promotion/inventory tool không mở trước VFBIZ-0034.
- Không mở bất kỳ Vehicle tool nào trước VFBIZ-0037/0038.
- Vision upload không mở trước verified association từ work item sau VFBIZ-0036.

## Validation và recovery

- Mỗi item lưu observed evidence và exact next action.
- Migration phải clean/legacy replay; contract phải compatibility/conformance.
- Failure chỉ dừng lane bị ảnh hưởng; không hạ scope bảo mật để “đạt demo”.
- Không dùng production PII, VIN hoặc VinFast fact chưa được duyệt.
