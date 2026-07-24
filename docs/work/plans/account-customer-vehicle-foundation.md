---
id: plan-account-customer-vehicle-foundation
title: ExecPlan Account, Customer Data và Vehicle Foundation
status: archived
owner_role: engineering-lead
scope: cross-system
when_to_read:
  - VFBIZ-0013
  - VFBIZ-0014
  - VFBIZ-0015
  - VFBIZ-0016
tags:
  - identity
  - customer
  - vehicle
  - security
revision: 2
review_date: 2026-08-23
supersedes: []
---

# Purpose

Triển khai foundation bắt buộc trước Chatbot: trust profile OIDC, Customer
Profile/Consent/DSAR, Vehicle Catalog được version hóa và Customer Garage tự khai
báo. Plan này điều phối dependency và exclusive resources; acceptance chi tiết
nằm trong từng work item.

## Progress

- [x] VFBIZ-0012: product, architecture, ownership và delivery order đã chốt.
- [x] VFBIZ-0013: Access principal và issuer policy.
- [x] VFBIZ-0014: Customer Profile, Consent và DSAR.
- [x] VFBIZ-0015: Vehicle Catalog release và structured data.
- [x] VFBIZ-0016: Customer Garage.

## Discoveries

- Public OpenAPI mô tả browser cookie/BFF nhưng NestJS runtime hiện chỉ nhận
  Bearer token và dùng một issuer; contract topology phải được làm rõ trước
  Customer API.
- `CustomerVehicleReference` đang trộn Garage, VIN và ownership verification;
  `OwnerVehicleAssociation` lại là projection rời chưa có provider authority.
- `VehicleVariant.specifications` và communication preferences đang là JSON
  không đủ schema cho business rule ổn định.

## Decisions

- Browser là same-origin BFF; resource API nhận access token từ BFF. Mobile sau
  này dùng Authorization Code + PKCE và cùng resource API.
- Identity, Customer, Product và Ownership là bounded context; “Account” chỉ là
  journey, không phải module catch-all.
- Catalog và Garage có thể được thiết kế độc lập nhưng migration/public contract
  là exclusive resource, nên integration owner tuần tự hóa các lần ghi.
- Không mở Conversation Runtime cho tới khi VFBIZ-0013–0016 đạt acceptance.

## Implementation phases

1. Multi-issuer trust policy, principal realm và negative token tests.
2. Customer vertical slices theo thứ tự Profile → Consent → DSAR.
3. Catalog revision/release read model và public projection.
4. Garage self-reported, không VIN và không verified ownership.
5. Cross-subject authorization, migration, contract/SDK và E2E.

## Validation

- `npm run verify:api`
- `npm run governance:check`
- Contract/runtime parity và generated SDK check.
- Cross-customer authorization, issuer isolation và migration replay.

## Rollback and recovery

Mỗi schema change dùng expand/migrate/contract. Không sửa migration đã áp dụng.
Activation của catalog release và module import là reversible; rollback không
được phục hồi semantics VIN/ownership đã bị loại bỏ nếu chưa có approved adapter.

## Outcome

Foundation đã hoàn tất ngày 2026-07-23 với API, migration replay, contract/SDK,
negative authorization và governance evidence. Conversation Runtime tiếp tục ở
ExecPlan riêng; plan này không còn được resolver chọn cho implementation mới.
