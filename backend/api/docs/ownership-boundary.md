---
id: api-ownership-boundary
title: Ranh giới quyền sở hữu phương tiện
status: active
owner_role: engineering-lead
scope: api
when_to_read:
  - vehicle-ownership
  - verified-vehicle
  - vin
tags:
  - ownership
  - privacy
  - quarantine
revision: 1
review_date: 2026-08-27
supersedes: []
---

# Ranh giới quyền sở hữu phương tiện

`ownership` chưa phải runtime NestJS context. Các bảng ownership legacy chỉ là
historical persistence và không chứng minh khách hàng sở hữu phương tiện.

## Invariants

- Không materialize `src/modules/ownership` trước khi có provider contract và
  approved use case.
- Không dùng `OwnerVehicleAssociation`, `ServiceAppointmentProjection` hoặc
  `externalVehicleRef` không định kiểu làm verified ownership.
- Customer Garage vẫn là self-reported và không cấp quyền Vision, recall,
  service, telematics hoặc capability dành riêng cho chủ xe.
- Không persist hoặc log raw VIN. Không tự tạo Vehicle Asset, tokenization,
  verification evidence hoặc dữ liệu DMS/CRM.

Materialize boundary này cần provider contract được phê duyệt, decision evidence
từ `VFBIZ-0036`, Privacy/Security/Data review và một controlled migration work
item riêng.

## Verify

Chạy `test/architecture/ownership-quarantine.spec.ts`, API lint và typecheck.
Test chặn source import, Prisma delegate/property access và raw SQL reference đã
biết. Nó không chứng minh raw VIN vắng mặt end-to-end và không thay thế migration
review, database permission, runtime telemetry hoặc privacy test.
