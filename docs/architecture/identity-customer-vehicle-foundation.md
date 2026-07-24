---
id: identity-customer-vehicle-foundation
title: Kiến trúc Identity, Customer và Vehicle foundation
status: active
owner_role: architect
scope: cross-system
when_to_read:
  - identity
  - customer-account
  - customer-profile
  - consent
  - dsar
  - vehicle-data
  - vehicle-catalog
  - customer-garage
  - vehicle-ownership
tags:
  - architecture
  - identity
  - customer
  - vehicle
revision: 2
review_date: 2026-08-23
supersedes: []
---

# Kiến trúc Identity, Customer và Vehicle foundation

## Trust boundary và system of record

```text
Customer Portal / Mobile
          |
      OIDC + BFF
          |
     API Platform
    /      |       \
 CIAM   API PostgreSQL   PIM/DMS/CRM adapters
          |
        Drupal
```

| Dữ liệu | Authority |
| --- | --- |
| Credential, MFA, email verification, identity session | CIAM/Keycloak |
| Opaque subject mapping, customer profile, consent, DSAR, garage | API |
| Model/variant/spec/price/availability | PIM/ERP projection qua API |
| Ownership/VIN verification | DMS/CRM projection qua API |
| Marketing copy, translation, SEO và web media | Drupal |
| AI state, retrieval và model release | AI Platform, sau foundation |

Không service nào sao chép credential. Client không gọi CIAM Admin API, database
hoặc AI Platform trực tiếp.

## Bounded contexts

### Security platform và Identity record

Security platform hiện sở hữu trust policy, token verification và
`AccessPrincipal`. `IdentitySubject` là record dùng chung, đang được provision
qua Customer adapter trong cùng transaction với Customer Profile. Chưa tạo
runtime module `access` riêng khi chưa có consumer cho session/revocation.
Khi boundary này được materialize, nó mới sở hữu mapping `(issuer, subject)`,
session projection và security event; việc chuyển ownership cần ADR/migration,
không chỉ di chuyển file.

### `customer`

Sở hữu Customer Profile, consent event, DSAR và Customer Garage. Garage là
reference/personalization khách hàng quản lý; nó không chứa VIN hoặc quyền
ownership. Association đã xác minh chỉ được liên kết vào garage để trình bày.

### `product`

Sở hữu public structured vehicle projection: model, variant, market
availability, critical typed specification, source revision và freshness.
Product không sở hữu editorial copy hoặc binary asset.

### `ownership` trong tương lai

Chỉ materialize khi có DMS/VIN/recall/service adapter thật. Foundation hiện chỉ
định nghĩa contract giữa garage và association, không import `ownership`
placeholder vào composition root.

## Account flow

1. CIAM hoàn tất Authorization Code flow; Portal dùng BFF cookie, mobile dùng
   Authorization Code + PKCE.
2. API verify access token bằng configured issuer/audience/JWKS allowlist.
3. Lần đầu truy cập `/me`, API upsert Identity Subject và Customer Profile trong
   một transaction idempotent.
4. API lấy subject từ verified principal, không nhận customer ID từ body/header.
5. Update profile dùng version precondition; consent ghi event mới; revoke
   session phải đồng bộ với CIAM adapter trước khi projection hoàn tất.
6. DSAR tạo orchestration job idempotent; xóa/tombstone tuân thủ legal hold và
   không ghi lại PII vào evidence.

## Vehicle data shape

### Stable identity

- Model và variant có UUID nội bộ cùng canonical code/slug ổn định.
- Market availability tách khỏi identity; một variant không bị nhân bản chỉ vì
  xuất hiện ở market khác.
- External source ID nằm trong mapping/projection metadata, không trở thành
  public primary key.

### Typed critical facts

Các field phục vụ authorization, filtering, range/charging, pricing hoặc safety
phải typed và có unit rõ: model year, body style, drivetrain, seats, battery
usable/gross capacity, range standard/value, AC/DC charging và connector.
Thông số mở rộng phải đi qua versioned specification schema; không đưa một
`specifications: any` trực tiếp ra public API.

### Bản đồ capability dữ liệu xe

Không phải mọi dữ liệu có chữ “xe” đều nằm trong một aggregate:

| Capability | Dữ liệu | Authority/lưu trữ |
| --- | --- | --- |
| Catalog identity | brand/model/variant code, slug, model year | API projection từ PIM |
| Commercial availability | market, trạng thái bán, effective window | API projection từ PIM/ERP |
| Technical specification | body style, kích thước, khối lượng, ghế, drivetrain, công suất/mô-men, wheel/tire | versioned Catalog revision |
| Battery/charging facts | gross/usable kWh, range + test standard, AC/DC kW, connector, charging curve reference | Catalog revision; curve chi tiết thuộc Mobility |
| Pricing/promotion | currency, amount, tax context, validity, eligibility | projection riêng từ ERP/Commerce, không nằm trong revision xe |
| Inventory/delivery | location, availability band, observed/freshness time | projection ngắn hạn, không phải Catalog fact |
| Media/editorial | gallery, video/3D, alt/focal, VI/EN copy, SEO | Drupal + DAM/object storage |
| Customer preference | claimed variant, nickname, primary | Customer Garage |
| Physical vehicle/ownership | Vehicle Asset, VIN token, verified association | DMS/CRM adapter tương lai |
| Aftersales/safety | warranty, recall eligibility, service history | Aftersales projection với authorization riêng |
| Telematics | SOC/location/odometer/event stream | telemetry platform; API chỉ giữ consent/grant và snapshot TTL ngắn |

Chỉ field có consumer hiện hữu và schema/source đã duyệt mới materialize thành
column. Taxonomy đầy đủ nằm trong capability map; không tạo một bảng khổng lồ,
EAV hoặc JSON vô danh để “dự phòng”.

### Source, release manifest và time

Mỗi model/variant/spec/price/availability pin `SourceRevision`. Catalog release
manifest pin membership và provenance theo entity/fact group để facts từ PIM,
homologation, battery engineering hoặc commerce không mượn một source chung.
Projection chỉ được public khi source `approved`, nằm trong effective window và
đáp ứng freshness policy. Last-known-good chỉ dùng khi policy của domain cho
phép và response phải hiển thị release ID, source revision, observed/expiry time
cùng availability.

Dynamic commercial facts là projection riêng:

- Price pin currency/amount minor, market, price type, tax/channel/eligibility
  và effective window.
- Promotion pin rule/benefit, stacking/eligibility và approval revision.
- Inventory pin location/variant, availability band, observed/expiry time.
- Anomaly gateway chặn dữ liệu mâu thuẫn trước khi API/AI tiêu thụ.

Chatbot chỉ nhận allowlisted application view. Nó không được đọc Prisma,
`extensionData`, raw provider response hoặc semantic-cache dynamic facts.

## Garage và VIN privacy

- Garage key là customer profile + garage UUID ngẫu nhiên; aggregate giữ
  `claimedVehicleVariantId`, nickname, primary/status và optional association ID.
- Variant được kiểm tra tồn tại, approved và nhất quán với model.
- `source` phân biệt `self-reported`, `dms`, `crm` và `support-assisted`.
- Garage không nhận VIN. Một Ownership Verification command riêng mới được phép
  nhận raw VIN trong request memory đủ để tokenization/provider lookup; Vehicle
  Asset lưu `vinTokenRef`, `maskedVin` và optional HMAC lookup fingerprint với
  key từ secret manager.
- Không dùng SHA-256 trần cho VIN vì không gian VIN có thể bị brute-force.
- Verification transition cần expected version, actor, evidence reference,
  correlation ID và audit event.

## Transaction và concurrency

- Provision subject/profile, profile update, consent, garage mutation,
  idempotency, audit và outbox commit trong transaction thích hợp.
- Unique constraint bảo vệ subject và source identity; optimistic version bảo
  vệ mutable aggregate.
- Mutation có thể retry dùng `Idempotency-Key`; cùng key khác request hash bị
  từ chối.
- Không giữ database transaction khi gọi CIAM/PIM/DMS; dùng adapter +
  reconciliation/outbox.

## Security và privacy

- Protected by default; public catalog là explicit `@Public()`.
- Portal session cookie dùng `HttpOnly`, `Secure` ở TLS, `SameSite` phù hợp và
  CSRF defense; browser không giữ token trong `localStorage`.
- Log/audit chỉ dùng opaque subject/internal IDs; email, phone, raw VIN, token
  và consent evidence payload bị redact.
- Customer/workforce issuer, audience và role namespace tách biệt.
- Rate limit login callback, `/me` mutation, session revoke, DSAR và garage VIN
  verification theo subject/IP/risk.

## Failure behavior

| Failure | Kết quả an toàn |
| --- | --- |
| Token/JWKS/issuer không hợp lệ | 401, không provision profile |
| Subject không có customer realm/profile | 403 |
| Update version stale | 409/412, không overwrite |
| CIAM revoke timeout | Projection giữ trạng thái pending và reconciliation |
| Catalog source thiếu/expired | Không trả fact hoặc đánh dấu unavailable theo policy |
| Variant không thuộc model | 422, không tạo garage reference |
| VIN provider chưa có/timeout | Giữ `unverified` hoặc `verification_pending` |
| DSAR target thất bại | Job partial/pending, retry hữu hạn và audit |

## Delivery slices

1. Access + current-customer profile foundation.
2. Consent, session projection và DSAR orchestration.
3. Vehicle catalog read model.
4. Customer Garage self-reported lifecycle.
5. DMS/VIN verification adapter sau khi có provider/contract thật.
6. Conversation Runtime và customer-scoped AI tool chỉ sau các slice trên.
