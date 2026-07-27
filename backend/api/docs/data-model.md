---
id: api-data-model
title: Data model và quyền sở hữu dữ liệu API Platform
status: active
owner_role: engineering-lead
scope: api
when_to_read:
  - schema
  - migration
  - persistence
  - data-ownership
tags:
  - prisma
  - postgresql
  - data
revision: 2026-07-24.2
review_date: 2026-08-22
supersedes: []
---

# Data model và quyền sở hữu dữ liệu của API Platform

## Ba loại record

1. **API-owned state:** customer profile, consent event, data request, garage,
   idempotency, audit, outbox và release decision.
2. **Projection/reference:** model, variant, price, trạm sạc, tariff, order,
   appointment. Mỗi record phải có source revision và freshness; API không tự
   biến projection thành system of record.
3. **Ephemeral/cache:** trip result và conversation projection. Record phải có
   expiry, policy/algorithm revision và không được dùng sau khi stale.

Không lưu credential/MFA secret, payment card, raw Google response, model secret,
embedding, prompt đầy đủ, file binary hoặc unredacted PII trong database này.

## Model theo bounded context

| Context | Aggregate/record chính | Bất biến quan trọng |
|---|---|---|
| `access` | `IdentitySubject`, `SessionProjection` | opaque subject; session reference được hash; revoke/expiry rõ ràng |
| `customer` | `CustomerProfile`, `ConsentEvent`, `CustomerDataRequest`, `CustomerGarageEntry` | profile dùng typed preferences + OCC; consent append-only/idempotent; DSAR có lifecycle; garage là self-reported, không phải ownership |
| `product` | `VehicleCatalogRelease`, stable `VehicleModel`/`VehicleVariant`, immutable revisions, `PriceProjection` | source, market, effective time, freshness và atomic release bắt buộc |
| `mobility` | `VehicleEnergyProfileRevision`, `ChargingLocation`, `ChargingEVSE`, `ChargingConnector`, availability/reliability observation, tariff revision/components và `TripPlan` | PostGIS location; thuật toán, route hash, source/cache policy và freshness được pin |
| `engagement` | `ConversationSession`, `ConversationInboxItem`, `ConversationEvent`, `ConversationCitation`, `SupportHandoff`, `TokenBudgetLedger`, `DeletionJob` | sequence/OCC/fencing; citation chuẩn hóa; retention và customer scope rõ |
| `operations` | `ReleaseOperation`, `ReleaseDecisionEvent`, `ReconciliationJob` | người yêu cầu không tự duyệt; evidence/correlation bắt buộc |
| `platform` | `SourceRevision`, `IdempotencyRecord`, `OutboxEvent`, `AuditEvent` | fail-closed khi provenance/approval thiếu; outbox cùng transaction nghiệp vụ |

`sales`, `ownership` và `commerce` giữ schema foundation nhưng không được mở
public workflow khi chưa có acceptance, authorization và adapter được phê duyệt.

## Conversation durability và knowledge revision

- `ConversationSession` pin profile, owner/capability hash, state version,
  active event sequence và retention.
- `ConversationInboxItem` giữ idempotency key, expected version, trạng thái
  claim, fencing token và cancellation reference; không giữ provider prompt.
- `ConversationEvent` là append-only business event cho public status, answer,
  citation, handoff và cancellation; hidden reasoning/raw tool payload bị cấm.
- `SupportHandoff` tồn tại độc lập với WebSocket và có queue/status/notification
  consent cùng operator audit.
- `TokenBudgetLedger` cộng dồn request/session/subject budget bằng atomic write.
- `KnowledgeRevisionProjection` phản chiếu domain/revision/state/freshness do AI
  publish; API không tự sửa nội dung knowledge.
- `DeletionJob` theo dõi idempotent DSAR fan-out và target còn lỗi, không sao
  chép payload đã yêu cầu xóa vào evidence.

## Conversation capability và object authorization

- Session `public_customer` nhận capability ngẫu nhiên 256-bit qua cookie
  `__Host-vfbiz_chat` có `HttpOnly`, `Secure`, `SameSite=Lax`; database chỉ lưu
  SHA-256 hash.
- Cookie chứa `session UUID.capability`, nên capability của một session không
  được replay cho session khác. Session hết hạn, đóng hoặc không tồn tại đều bị
  từ chối bằng cùng failure shape.
- Session `authenticated_customer` liên kết đến `CustomerProfile` và được kiểm
  tra đồng thời `issuer` + `subject`; bearer token không tự cấp quyền truy cập
  một conversation khác.
- Cookie, bearer token và capability không được ghi vào log, audit metadata hoặc
  analytics. Response conversation dùng `Cache-Control: no-store`.

## Trip data minimization và retention

- Charging projection chuẩn hóa theo `Location → EVSE → Connector`; không dùng
  một connector record cùng `unitCount` để đại diện nhiều EVSE vật lý.
- Availability là observation theo thời điểm, không ghi đè identity/configuration
  của EVSE hoặc connector. Tariff dùng immutable revision, element, price
  component, timezone và effective window.
- OCPI là interoperability reference cho location/EVSE/connector/tariff; OCPP
  nằm sau CSMS/V-GREEN adapter và không phải customer-facing contract.
- Mọi đường ghi trip projection phải pseudonymize provider place identifier
  bằng một key tách biệt; raw address, coordinate, polyline, geocoded
  waypoint và provider response không được ghi vào projection.
- Persistence dùng allowlist và từ chối field ngoài schema trước khi gọi
  repository. Projection luôn ghi nhận rằng raw provider payload không được lưu.
- `retentionUntil` phải sau `calculatedAt`; cache `expiresAt` không được vượt
  retention. Purge chạy theo batch có giới hạn để tránh lock dài và loop vô hạn.
- Pseudonymization key đến từ secret manager. Thay key cần migration/retention
  plan vì hash cũ không thể đối chiếu với hash mới.
- Exact origin/destination chỉ được giữ trong thời gian xử lý hoặc retention đã
  duyệt; log/analytics không được suy diễn hay gắn nhãn home/work nếu thiếu
  purpose và consent.

## Domain model không đồng nghĩa Prisma model

Prisma model là persistence record. Domain entity/value object nằm trong
`src/modules/<context>/domain`, bảo vệ business invariant và không import
NestJS/Prisma. Mapping giữa hai loại model nằm trong
`infrastructure/persistence`; controller không trả Prisma record trực tiếp.

## Customer account foundation

- `CustomerProfile` lưu `displayName`, locale, IANA timezone, market và ba
  communication preference boolean tách biệt; không dùng JSON tùy ý.
- `version` là optimistic concurrency token và được expose bằng ETag. Update
  thiếu hoặc stale `If-Match` bị từ chối.
- `ConsentEvent` dùng allowlist purpose cùng enum state/source ở application
  boundary, append-only và pin hash của idempotency key + request.
- `ConsentPolicy` là registry được phê duyệt theo purpose/version, checksum,
  effective window và approval evidence; client không thể tự tạo policy bằng
  cách gửi một chuỗi version mới. Mỗi purpose chỉ có một policy `active`.
- `CustomerDataRequest` là aggregate điều phối export/delete. Khi intake, nó
  snapshot `CustomerDataRequestTarget` theo registry version và tạo
  `CustomerDataRequestEvent` append-only trong cùng transaction với audit và
  outbox. Target giữ phase, retry, lease/fencing, outcome và private artifact
  reference; không trả object URL hoặc provider error qua customer API.
- Foundation hiện mới cung cấp intake + subject-scoped status. Không coi target
  `pending` là bằng chứng đã xóa/xuất dữ liệu; completion chỉ hợp lệ sau khi mọi
  target bắt buộc có evidence hoặc legal-retention decision được đúng authority
  phê duyệt.
- `(issuer, subject)` được provision idempotently thành `IdentitySubject`; chỉ
  principal realm `customer` có thể tạo Customer Profile.
- `SourceRevision.observedAt` là mốc freshness; `effectiveAt` chỉ là mốc hiệu
  lực nghiệp vụ và không được dùng thay thời điểm quan sát/ingest.
- Source dùng enum `approvalState` và `classification`, pin
  `submittedByRef`, `approvedByRef`, approval evidence, permitted purpose,
  license, checksum và ingestion time. Database từ chối source mang trạng thái
  approved nếu còn placeholder hoặc người submit tự approve.

## Vehicle Catalog và Customer Garage foundation

- Stable model/variant giữ identity; tên, trạng thái thương mại và specification
  nằm trong immutable revision của một atomic Catalog release.
- `VehicleFactProvenanceBinding` pin source theo release/model/variant và bốn
  fact group typed. Binding này là release manifest evidence, không phải EAV
  cho specification.
- Typed baseline hiện materialize seat, drivetrain, battery gross/usable,
  declared range + test standard, AC/DC charge power và connector. Long-tail
  chỉ nằm trong `extensionData` đã pin `specificationSchemaVersion`; public API
  không expose object này.
- Dimensions, mass, power, torque, wheel/tire, warranty và homologation chỉ
  promote thành typed field khi có approved source schema và consumer thật.
- `CustomerGarageEntry` lưu claimed variant, nickname, primary/status/source,
  create idempotency hashes, optimistic version và timestamps.
- Profile/Garage mutation tái xác minh subject + profile active ở bên trong
  serializable transaction. State, redacted audit và versioned outbox event là
  một atomic unit; downstream không được suy diễn thành ownership verification.
- Garage không lưu raw VIN, masked VIN hoặc verification state. Verified
  ownership sau này dùng `VehicleAsset` và association riêng.
- Create kiểm variant bằng Product application port: đúng market, active,
  approved, effective và fresh. Idempotent replay được giải quyết trước current
  catalog validation.

## Migration policy

- Không sửa migration đã merge/applied.
- Dùng expand → backfill → contract khi có dữ liệu đang hoạt động.
- Migration phải fail closed nếu không thể suy ra dữ liệu thật; không điền giá,
  model, VIN hoặc provenance giả chỉ để vượt `NOT NULL`.
- Review SQL cho drop/rename, lock dài, unique collision, orphan foreign key,
  PII, extension và rollback/forward recovery.
- `migrate dev` chỉ dùng database cô lập; deployment dùng `migrate deploy`.
