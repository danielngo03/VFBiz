---
id: api-vehicle-catalog-and-garage
title: Vehicle Catalog, Customer Garage và Ownership boundary
status: active
owner_role: engineering-lead
scope: api
when_to_read:
  - vehicle-data
  - vehicle-catalog
  - customer-garage
  - vehicle-ownership
  - vin
tags:
  - nestjs
  - product
  - vehicle
  - garage
revision: 8
review_date: 2026-08-23
supersedes: []
---

# Vehicle Catalog, Customer Garage và Ownership boundary

## Ba aggregate không được trộn

1. `product`: structured Vehicle Catalog projection.
2. `customer`: Customer Garage preference/reference.
3. `ownership`: physical Vehicle Asset và verified Customer Vehicle
   Association, chỉ materialize khi có DMS/VIN adapter thật.

Garage entry không phải bằng chứng ownership. Biết VIN, garage UUID hoặc
`has_vehicle=true` không cấp quyền đọc recall, service hoặc telematics.

## Vehicle Catalog

### Stable identity

`VehicleModel` giữ stable UUID, `brandCode`, `modelCode` và slug.
`VehicleVariant` giữ stable UUID, model ID và `variantCode`. Tên hiển thị,
market, model year và commercial status thuộc immutable release revision, không
được ghi đè lên stable identity. External source ID không làm public primary
key.

### Atomic release và provenance

Catalog publish dùng:

- `VehicleCatalogRelease`: market, release manifest, state, effective/activate/
  supersede timestamps; tối đa một active release mỗi market.
- immutable `VehicleModelRevision` và `VehicleVariantRevision` thuộc release;
- typed specification hiện nằm trong `VehicleVariantRevision`; khi tách thành
  specification set riêng phải giữ nguyên atomic membership và schema version.

Approved revision không update tại chỗ. Current read chỉ lấy atomic active
release, không join model của revision A với variant/spec của revision B.

Release lifecycle hiện được enforce ở ba lớp:

- domain state machine giữ `draft → approved → active → superseded` và rollback
  chỉ từ một revision đã từng được activate;
- PostgreSQL check constraint giữ evidence/timestamp đúng với từng state và
  cấm submitter tự approve;
- application repository dùng optimistic concurrency theo `revision` cùng
  PostgreSQL advisory transaction lock theo market, nên hai activation đồng
  thời không thể cùng trở thành current release.

Approve, activate, supersede và rollback ghi `AuditEvent` cùng `OutboxEvent`
trong chính serializable transaction. Advisory lock chỉ serialize thao tác
release theo market; nó không thay thế OCC hoặc unique constraint.

Workforce release commands hiện nằm dưới
`/api/v1/operations/releases/vehicle-catalog/*`, bị loại khỏi public OpenAPI và
chỉ nhận workforce token có MFA evidence. `vehicle-data-reviewer` được approve;
`vehicle-data-operator` được activate/rollback. Actor luôn lấy từ verified
subject, không nhận từ body/header. Database vẫn enforce submitter khác
reviewer, nên role không thay separation of duties.

Một release-level source không đủ để chứng minh mọi fact. Manifest phải pin
provenance theo entity hoặc fact group, tối thiểu:

- identity/commercial status;
- technical/homologation;
- battery/range/charging;
- option/compatibility;
- từng commercial projection tách biệt.

Mỗi provenance binding có source ID/revision/checksum, observed time, effective
window, classification, rights/usage policy và approval evidence. Requester
không được tự approve release của chính mình.

Schema hiện có `VehicleFactProvenanceBinding` với subject typed
`release|model|variant` và bốn fact group ở trên. Source đã dùng vocabulary
typed, permitted purpose và database separation-of-duties constraint. Public
reader kiểm membership của mọi binding, coverage theo fact thực sự được expose
và eligibility của từng source. Binding trỏ entity ngoài release, thiếu fact
group, source không `public`, stale, sai purpose hoặc thiếu approval evidence
đều làm toàn release unavailable.

Runtime hiện có `GET /api/v1/vehicles/models` và `/{slug}`. Presenter chỉ đọc
release `active` có SourceRevision `approved`, classification `public`,
effective và còn fresh; không có release đạt gate thì trả
`VEHICLE_CATALOG_UNAVAILABLE`, không fallback về legacy column hoặc fixture.

### Typed facts và long tail

Typed field khi dùng để filter, compare, energy, pricing hoặc safety:

- category/body style, generation/model year, drivetrain và seats;
- gross/usable battery capacity;
- declared range value + test standard;
- AC/DC charge limit và connector standard;
- dimensions, curb/gross weight, power/torque và wheel/tire khi có approved
  source/consumer;
- exterior color, interior trim, wheel/package và option compatibility khi
  configurator/chatbot cần tư vấn cấu hình.

Long-tail specification được lưu trong object có `schemaVersion` và validation
contract. Không trả `Json/any` trực tiếp qua public presenter. Field được
filter/sort thường xuyên phải được promote thành typed column; không tạo EAV/
GIN index khi chưa có query plan.

Controlled vocabulary không dùng string tùy ý cho body style, drivetrain, range
test cycle, connector hoặc unit. Không có nguồn được duyệt thì trả
`unavailable`, không tạo placeholder giống dữ liệu thật.

Schema hiện dùng stable `VehicleModel`/`VehicleVariant` và immutable
`VehicleModelRevision`/`VehicleVariantRevision`. Migration đưa legacy JSON vào
`extensionData` với `legacy-v1`; public presenter không expose object này.

### Source, effective time và freshness

Source policy và ingestion revision là hai khái niệm. Tối thiểu mỗi release pin:

- source/owner/provenance/license/classification;
- external revision và checksum;
- observed/ingested/effective/expiry time;
- approval state/evidence;
- freshness policy.

Default `unassigned`, `UNVERIFIED` hoặc `pending` không bao giờ được activate.
Effective time không được dùng thay freshness time.

### Seed, source candidate và import

`prisma/seed` chỉ phục vụ hai trường hợp:

1. `seed:validate` kiểm metadata của Source Candidate và không ghi database.
2. `seed:local` tạo một Catalog hoàn toàn synthetic để phát triển và chạy test
   trên PostgreSQL loopback.

Synthetic seed phải có opt-in rõ, bị cấm trong production, không được ghi đè
một active release khác và phải đổi source/release version nếu fixture thay
đổi. Nhãn hiệu, model, giá và thông số trong fixture không được giả làm dữ liệu
VinFast.

Nguồn Website/PDF công khai được đăng ký trước dưới dạng Source Candidate.
Candidate chỉ chứa metadata như publisher, document code, URL, market và ngày
hiệu lực. Nó không phải `SourceRevision` đã được phê duyệt và không được phép
download/import cho đến khi có:

- quyền sử dụng và permitted purpose do Data/Legal Owner xác nhận;
- checksum SHA-256 của artifact đã quan sát;
- submitted/approved actor tách biệt;
- approval evidence và freshness policy;
- parser version cùng reconciliation evidence.

Robots/content signal, điều khoản Website và trạng thái public không tự thay thế
quyền sử dụng nội bộ. Dữ liệu được phép dùng làm tham chiếu cho Catalog cũng
không tự động được phép đưa vào RAG hoặc AI training.

Luồng production dự kiến là:

```text
Source Candidate
  → rights approval
  → controlled fetch vào quarantine
  → checksum/malware/schema validation
  → parser output + reconciliation
  → DRAFT Catalog/Commercial release
  → independent approval
  → atomic activation
```

Không dùng Prisma seed làm production ingestion job. Ingestion production phải
đi qua application service, audit, outbox, idempotency và release operation.

### Drupal/media boundary

Drupal sở hữu localized title/copy, SEO, campaign, gallery order, alt/focal
point và web composition. DAM/object storage sở hữu binary. API sở hữu canonical
catalog ID và structured fact. Chỉ thêm media projection vào API khi portal/
mobile có consumer thật.

## Customer Garage

`CustomerGarageEntry` là API-owned personalization:

- `id`, `customerProfileId`, `claimedVehicleVariantId`;
- `nickname`, `isPrimary`, `status=active|archived`;
- `source=self-reported|imported`, `version`, timestamps.

`vehicleAssociationId` chưa tồn tại trong foundation. Chỉ thêm liên kết đó sau
khi `ownership` có DMS/VIN adapter, authorization và lifecycle được duyệt.

Invariant:

- entry chỉ tham chiếu variant hợp lệ cho market;
- một customer có tối đa một primary active entry;
- update/archive dùng expected version;
- query luôn subject-scoped;
- self-reported entry không cấp ownership scope;
- DSAR/archive behavior theo Customer policy.

Trong foundation hiện tại, create từ customer chỉ được ghi
`source=self-reported`. Giá trị `imported` chỉ được dùng bởi adapter có
provenance, correlation, idempotency và authority riêng; client không được chọn
source.

## Ownership/VIN trong tương lai

Chỉ materialize khi provider và consumer được duyệt:

- `VehicleAsset`: verified variant mapping, tokenized external ref,
  `vinTokenRef`, optional keyed HMAC fingerprint, minimal mask, source/freshness.
- `CustomerVehicleAssociation`: vehicle asset + customer + relationship type
  (`owner`, `authorized_driver`, `fleet_user`), validity và status.
- `OwnershipVerificationCase`: method/provider, state/reason, idempotency,
  evidence object ref, retention và timestamps.

Raw VIN chỉ tồn tại trong request memory cho tokenization/provider lookup.
Không log/audit/outbox/fixture/database. Không SHA-256 VIN trần; exact-match chỉ
dùng keyed HMAC với key/rotation trong secret manager. Không index `maskedVin`.

```text
Garage entry
  -> verification case
  -> success: create/activate association and link entry
  -> rejection: entry vẫn self-reported
  -> transfer/revoke: end-date association, không rewrite history
```

## Energy, service, recall và telematics

- Energy profile thuộc `mobility`, pin purpose/algorithm/source/validity; nó là
  planning assumption, không tự nhận là homologated catalog fact.
- Service appointment là DMS/dealer projection và phải join Vehicle Asset,
  không join raw external/VIN string.
- Recall tách public campaign khỏi customer-scoped vehicle eligibility; dữ liệu
  safety stale phải unavailable/handoff.
- Raw/high-volume telematics không vào API PostgreSQL. API chỉ giữ grant/consent
  và snapshot TTL ngắn khi có owner/use case.

## Commercial fact và inventory

Price, promotion và inventory không nằm trong Catalog release:

- `PriceOffer`: variant, market, currency, amount, tax context, price type,
  channel/eligibility, validity và source revision.
- `Promotion`: rule/benefit có version, eligibility, stacking policy, validity
  và approval revision.
- `InventoryObservation`: location/variant/availability band, observed time,
  expiry và source; không biến observation thành lời hứa giao xe.
- `CommercialFactAnomaly`: rule version, fact reference, severity, disposition
  và evidence; fact bị conflict không được chuyển cho chatbot.

Schema hiện dùng `CommercialDataRelease` để activate atomic price/promotion
set theo market; `InventoryObservation` vẫn độc lập vì expiry ngắn và cadence
khác. Commercial release có cùng separation-of-duties, evidence, revision và
partial unique active-market invariant như Catalog release. Legacy
`PriceProjection` được migrate thành `PriceOffer` trong release `draft`, tuyệt
đối không tự nâng dữ liệu cũ thành public.

`PriceOffer` pin `offerCode`, `priceType`, amount-minor dạng integer, currency,
tax treatment, channel, eligibility schema/rules, validity và SourceRevision.
`Promotion` pin code + version, scope model/variant, benefit typed, stacking
policy, eligibility và validity. JSON chỉ dùng cho rules/benefit long tail có
schema version; field query/anomaly critical vẫn là typed column.

`InventoryObservation` pin stable variant, location ref, availability band,
optional unit count, observed/expiry và SourceRevision. Public commercial API
không expose inventory trong foundation vì chưa có DMS/provider contract và
availability có thể bị hiểu thành lời hứa giao xe.

`CommercialFactAnomaly` trỏ chính xác một fact. Blocking anomaly ở trạng thái
`open` hoặc `accepted` làm read path fail closed; chỉ false positive `rejected`
hoặc anomaly đã `resolved` mới không chặn. Amount range là versioned business
policy theo market/price type, không hard-code một ngưỡng dùng cho option,
service và vehicle MSRP.

Public endpoint hiện có
`GET /api/v1/vehicles/models/{slug}/commercial`. Endpoint trả amount-minor dưới
dạng decimal string để không mất chính xác qua JavaScript, kèm release version,
validity và source/freshness cho từng fact. Không có active/fresh/anomaly-free
release thì trả `VEHICLE_COMMERCIAL_DATA_UNAVAILABLE`.

Dynamic facts chỉ dùng micro-TTL session cache theo subject/capability. Không
đưa giá, promotion hoặc inventory vào RAG, model memory hay semantic cache
toàn cục.

Commercial release dùng cùng lifecycle/OCC/audit/outbox/market lock nhưng có
publication gate riêng: source phải được duyệt và current, release phải có price
offer, market phải khớp, amount phải qua anomaly policy, mọi source con phải đúng
purpose và không có blocking anomaly. Workforce route tách role
`commercial-data-reviewer` với `commercial-data-operator`; reviewer không thể
approve release do chính subject đó submit.

## Allowlisted Vehicle Facts view cho Chatbot

Chatbot không đọc Prisma, `extensionData` hoặc raw adapter payload. Product
application xuất một read-only `VehicleFactsToolView` có:

- stable model/variant identity, market và release ID;
- allowlisted typed fact cùng unit;
- `sourceId`, source revision/checksum, `observedAt`, `effectiveFrom`,
  `effectiveTo`/`expiresAt` và availability state;
- catalog/commercial anomaly state;
- public citation reference phù hợp.

Garage tool chỉ nhận self-reported view đã tối thiểu hóa. Price/promotion/
inventory tool là operation riêng và fail-closed khi stale/anomalous. Recall,
service, Vision hoặc telematics chỉ mở sau verified Vehicle Association.

## Index và constraint tối thiểu

- Unique `(brandCode, modelCode)`.
- Unique `(vehicleModelId, market, variantCode)`.
- Unique release membership `(entityId, catalogReleaseId)`.
- Partial unique active catalog release mỗi market.
- Garage index `(customerProfileId, status, updatedAt)` và partial unique primary.
- Association index `(customerProfileId, status)` và `(vehicleAssetId, status)`.
- Verification request hash unique, state/request time indexed.
- Không index raw/masked VIN hoặc JSON khi chưa có approved need.

Critical invariant phải có domain test và database constraint khi PostgreSQL có
thể diễn đạt an toàn.

## Read/API behavior

- Public list/detail yêu cầu market và trả release/source/freshness.
- Compare pin cùng catalog release.
- Garage list/add/update/archive trả rõ `self-reported` và derived ownership
  status; client không được gửi `verified`.
- Verification dùng command riêng, idempotent và không có endpoint đọc lại VIN.
- Customer-scoped AI tool sau này chỉ nhận allowlisted garage/association view
  từ API; stale/unauthorized trả typed failure.

## Required tests

- Atomic release không trộn revision; unapproved/expired source không public.
- Commercial release không trả price/promotion stale, ngoài validity, lệch
  market hoặc có blocking anomaly.
- Amount/currency/validity, promotion benefit shape, inventory expiry và
  anomaly target được enforce bằng PostgreSQL constraint.
- Provenance theo fact group không bị thay bằng một release-level source chung.
- Model/variant/market consistency và duplicate stable key.
- Typed specification/unit/schema validation.
- Runtime route inventory khớp reviewed OpenAPI và generated SDK.
- Cross-customer garage denial, primary uniqueness và OCC.
- Customer input không thể đặt ownership verified.
- Raw VIN không xuất hiện trong persistence, log, audit, outbox hoặc response.
- Provider timeout không biến garage entry thành verified.
- Tool view không lộ Prisma record, `extensionData` hoặc fact thiếu freshness.
- Drupal composition chỉ dùng canonical catalog reference.
