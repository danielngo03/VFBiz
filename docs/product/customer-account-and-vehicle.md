---
id: customer-account-and-vehicle
title: Nền tảng tài khoản khách hàng và dữ liệu xe
status: active
owner_role: product-owner
scope: cross-system
when_to_read:
  - identity
  - customer-account
  - customer-profile
  - customer-data
  - vehicle-data
  - vehicle-catalog
  - customer-garage
tags:
  - product
  - account
  - customer
  - vehicle
revision: 3
review_date: 2026-08-23
supersedes: []
---

# Nền tảng tài khoản khách hàng và dữ liệu xe

## Outcome

Khách hàng có một danh tính nhất quán, quản lý được hồ sơ, consent, session và
yêu cầu dữ liệu của chính mình. Hệ thống có catalog xe có nguồn/revision rõ
ràng và một Customer Garage phân biệt chính xác xe tự khai báo với xe đã được
xác minh. Foundation này phải tồn tại trước khi Chatbot được phép đọc dữ liệu
khách hàng hoặc đưa ra câu trả lời liên quan tới xe.

## Các hành trình nền tảng

### Tài khoản

- Đăng ký, xác minh email, đăng nhập, khôi phục tài khoản và MFA do CIAM thực hiện.
- Portal/mobile nhận authorization thông qua OIDC; API không nhận password.
- Khách hàng xem và cập nhật hồ sơ tối thiểu của chính mình.
- Khách hàng xem/revoke session, ghi consent và tạo yêu cầu export/delete.
- Mọi thao tác subject-scoped đều kiểm tra object authorization tại API.

### Catalog xe

- Client lấy danh sách model/variant đang có hiệu lực cho đúng market.
- Mỗi fact group có source revision/checksum, observed/effective time và
  freshness; một source chung của release không được dùng để che provenance
  khác nhau giữa homologation, battery, charging và option.
- Các trường quan trọng cho search, compare, safety và energy được typed; dữ
  liệu mở rộng dùng schema có version, không dùng JSON vô danh.
- Marketing copy, translation và web media do Drupal sở hữu; API chỉ giữ
  structured product identity/specification và asset reference cần tích hợp.

### Customer Garage

- Khách hàng thêm variant vào garage với nguồn `self-reported`.
- Garage entry tự khai báo không bao giờ được dùng như ownership đã xác minh.
- VIN không được lưu plaintext; chỉ lưu token reference, mask và keyed lookup
  fingerprint khi có provider verification được phê duyệt.
- UI có thể trình bày ownership status `unverified`, `verification_pending`,
  `verified` hoặc `rejected`, nhưng trạng thái này được suy từ verification case
  và association riêng, không phải flag khách hàng sửa trên garage entry.
- Xóa garage reference không mặc nhiên xóa record DMS/CRM hoặc lịch sử audit.

## Phạm vi dữ liệu

### API-owned

- Opaque identity subject mapping.
- Hồ sơ hiển thị tối thiểu, locale, timezone, market và preference.
- Consent event append-only, data request, session projection.
- Customer garage entry, nickname và primary preference. Verified association
  chỉ được liên kết sau khi Vehicle Asset/DMS contract được phê duyệt.
- Audit, idempotency và outbox.

### Projection có nguồn bên ngoài

- Model, generation/model year, variant/trim và market availability.
- Body style, dimensions/weight, drivetrain, seat count, power/torque,
  battery/charging/range, color/trim/option compatibility đã được duyệt.
- Price/tax/channel, promotion/eligibility, inventory/location/freshness.
- Ownership/VIN verification, warranty, recall và service state khi có
  authoritative provider.
- Mọi projection cần source, revision, effective time và freshness.

### Không lưu trong API database

- Password, password hash, MFA secret, recovery code hoặc raw refresh token.
- Raw VIN, giấy tờ xe, ảnh giấy tờ hoặc license plate nếu chưa có use case và
  privacy approval.
- Payment card, raw provider response, binary media hoặc editorial content.
- Dữ liệu telematics/live location trong Account/Garage foundation.

## Acceptance

- Customer A không đọc/sửa profile, session, consent, data request hoặc garage
  của Customer B.
- Subject lần đầu được provision idempotently bằng `(issuer, subject)` và không
  tạo profile trùng khi request đồng thời.
- Profile update dùng optimistic version/ETag và từ chối lost update.
- Consent không bị overwrite; current state được suy từ event mới nhất.
- Data request trùng correlation/idempotency key không tạo hai yêu cầu.
- Catalog không trả record thiếu approved source hoặc đã hết freshness policy.
- Catalog release có separation-of-duties, atomic activate/rollback và
  provenance theo fact group.
- Garage kiểm variant/model consistency và không nhận VIN; verification command
  riêng mới được xử lý VIN trong memory.
- `verified` chỉ đến từ authorized ownership adapter, không từ customer input.
- Public contract, migration, negative authorization và E2E có evidence trước
  khi staging acceptance.
- Chatbot chỉ nhận allowlisted Vehicle Facts view; không nhận Prisma record,
  `extensionData`, raw provider payload hoặc dynamic fact đã stale/anomalous.

## Non-goals của foundation

- Chưa tích hợp DMS/VIN production, telematics, recall hoặc service booking.
- Chưa lưu địa chỉ giao hàng, payment profile hoặc dữ liệu checkout.
- Chưa cho Chatbot đọc Customer Garage; việc đó cần Conversation Runtime,
  customer-scoped tool và AI release riêng.
- Customer Portal chỉ triển khai account, security, privacy/DSAR và
  self-reported Garage trong current scope; chưa có discovery mua xe đầy đủ.
- Chưa xây mobile account screens.
