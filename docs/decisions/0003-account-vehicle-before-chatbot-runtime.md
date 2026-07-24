---
id: adr-0003-account-vehicle-before-chatbot-runtime
title: ADR 0003 — Account và Vehicle foundation trước Chatbot runtime
status: active
owner_role: architect
scope: cross-system
when_to_read:
  - delivery-order
  - identity
  - vehicle-data
  - customer-chatbot
tags:
  - adr
  - account
  - vehicle
  - chatbot
revision: 1
review_date: 2026-08-23
supersedes: []
---

# ADR 0003 — Account và Vehicle foundation trước Chatbot runtime

## Status

Accepted cho delivery sequencing và bounded-context activation. Product,
Security, Privacy và Release Owner vẫn phải duyệt acceptance/release tương ứng.

## Context

ADR 0002 đã chốt kiến trúc Chatbot V6 nhưng để Account và Vehicle ở roadmap.
Chatbot authenticated cần customer identity, subject-scoped authorization,
garage và trusted vehicle projection. Nếu triển khai Conversation Runtime trước,
team AI sẽ buộc phải dựa vào fixture hoặc tự tạo customer/vehicle authority.

## Decision

1. Delivery order đổi thành Identity/Account → Customer Data → Vehicle
   Catalog/Garage → Conversation Runtime → LangGraph/RAG.
2. ADR 0002 vẫn là nguồn chuẩn cho kiến trúc Chatbot; ADR này chỉ thay thứ tự
   implementation, không thay AI trust boundary.
3. Materialize `access`, `customer` và `product` NestJS module theo vertical
   slice khi có controller/use case/test thật. Không khôi phục module rỗng.
4. CIAM sở hữu credential/MFA; API chỉ lưu opaque subject và projection cần
   business authorization.
5. Browser dùng same-origin BFF: BFF giữ token server-side và phát opaque
   `HttpOnly` cookie; resource API nhận bearer do BFF chuyển tiếp. Mobile dùng
   Authorization Code + PKCE và secure native storage. Không để SPA giữ token.
6. Customer và workforce dùng issuer/audience/client/session namespace riêng.
   API chỉ nhận issuer nằm trong allowlisted policy; không discovery JWKS từ
   `iss` tùy ý.
7. BFF auth/session contract và resource API contract phải tách rõ host/trust
   boundary; CI chặn security scheme khác runtime.
8. API-owned Customer Garage và external ownership verification là hai khái
   niệm khác nhau. `verified` chỉ đến từ authorized adapter/evidence.
9. Structured vehicle fact thuộc API projection; editorial content thuộc
   Drupal. AI chỉ đọc qua authorized API tool sau này.
10. Public contract v1 giữ additive compatibility; migration theo expand →
   backfill → contract và fail closed với PII/provenance chưa rõ.

## Consequences

- Chatbot delivery chậm lại một nhịp nhưng không phải xây identity/vehicle mock
  thành production dependency.
- API Platform có thêm ba bounded module thực; cần migration, authorization và
  negative E2E evidence.
- Customer Portal/mobile có contract ổn định hơn và dùng cùng generated SDK.
- DMS/PIM/CRM vẫn là adapter tương lai; staging dùng synthetic versioned source.
- BFF và resource API không thể tiếp tục dùng một OpenAPI security scheme mơ hồ;
  contract cleanup là release gate trước khi expose Account.

## Rejected alternatives

- Để AI Platform lưu customer profile/garage: phá system-of-record và ACL.
- Lưu password/VIN plaintext trong API: tăng breach impact không cần thiết.
- Một module `account-vehicle-chatbot`: trộn lifecycle và ownership.
- Tạo đầy đủ ownership/service/telematics module ngay: chưa có provider/use case.
- Dùng JSON tự do cho toàn bộ specification: khó validate, compare và phát hiện
  anomaly.

## Verification

Quyết định được coi là implemented khi các work item riêng có observed evidence
cho subject provisioning, object authorization, profile OCC, consent append-only,
DSAR idempotency, catalog source/freshness, garage verification lifecycle,
migration và public contract compatibility.
