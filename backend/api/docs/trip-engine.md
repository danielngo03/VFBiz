---
id: api-trip-engine
title: Trip Engine của API Platform
status: active
owner_role: engineering-lead
scope: api
when_to_read:
  - ev-trip-planner
  - charging-data
  - route-provider
  - energy-model
  - location-privacy
  - trip-correctness
context_anchors:
  ev-trip-planner: "## Public contract"
  charging-data: "## Canonical charging model"
  route-provider: "## Provider adapter"
  energy-model: "## Planner components"
  location-privacy: "## Privacy và persistence"
  trip-correctness: "## Kiểm thử bắt buộc"
tags:
  - mobility
  - trip-planner
  - postgis
  - privacy
revision: 1
review_date: 2026-10-24
supersedes: []
---

# Trip Engine của API Platform

## Ownership

Context `mobility` sở hữu public Station Discovery/Trip Plan contract,
deterministic planning policy, provider orchestration, trip persistence và
location privacy enforcement. Nó không sở hữu Product catalog, Customer
Garage, chatbot orchestration, charger protocol hoặc live navigation.

Product context cung cấp approved vehicle/variant reference. Customer context
resolve Garage entry thuộc subject. V-GREEN/CSMS projection cung cấp charging
facts; Google adapter chỉ cung cấp place/route content theo provider terms.

## Dependency rule

```text
presentation/http
        ↓
application commands, queries và ports
        ↓
domain energy, charging và trip
        ↑
infrastructure persistence, providers và workers
```

Controller chỉ parse/map HTTP. Application service điều phối authorization,
transaction và port. Domain không import NestJS, Prisma hoặc provider SDK.
Provider DTO được map tại adapter; code trong domain không phụ thuộc Google,
OCPI version hoặc V-GREEN field name.

Không tạo `common`, `helpers`, `utils` hoặc provider-named top-level module.
Folder/layer chỉ được tạo khi có implementation và test thật.

## Public contract

```text
GET  /api/v1/trip/vehicle-profiles
GET  /api/v1/charging/locations
GET  /api/v1/charging/locations/{locationId}
POST /api/v1/trip/plans
GET  /api/v1/trip/plans/{planId}
POST /api/v1/trip/plans/{planId}/cancel
```

Create plan cần `Idempotency-Key`; authenticated plan luôn kiểm subject/object
scope. Public plan nếu được mở phải dùng unguessable scoped capability và
retention riêng, không chỉ dựa vào biết UUID.

`POST` persist job rồi trả `202`. State hợp lệ:

```text
queued -> routing -> evaluating_stops -> completed
   |          |              |
   +----------+--------------+-> failed
   +---------------------------> cancelled
```

Transition dùng OCC. Worker claim bằng lease/fencing token. Cancellation gửi
best-effort tới route provider nhưng output từ lease/token cũ luôn bị từ chối.
Plan terminal không được quay lại trạng thái processing.

Response/error dùng OpenAPI-reviewed DTO và RFC Problem Details. Không trả raw
provider payload, internal score, SQL/PostGIS detail hoặc privacy policy.

## Canonical charging model

- `ChargingLocation`: site, address projection, access/opening metadata và
  spatial point.
- `ChargingEVSE`: một điểm phục vụ một xe tại một thời điểm.
- `ChargingConnector`: standard, format, voltage/current/power và capability.
- `ChargingAvailabilityObservation`: status theo EVSE/connector, source,
  observed time và quality.
- `ChargingTariffRevision`: currency, effective window và ordered element.
- `TariffElement/PriceComponent`: energy, time, session, parking và restriction.
- `ChargingReliabilitySnapshot`: aggregation có method/revision, không phải
  live fact.

OCPI là external reference, không phải internal persistence schema. OCPP được
terminate tại CSMS/V-GREEN; Mobility chỉ nhận governed projection/event.
Không dùng `unitCount` thay cho EVSE và không suy diễn EVSE giả khi source thiếu.

Migration khỏi schema transitional phải là work item controlled riêng, có
exclusive lease, data mapping evidence và expand → backfill → contract.

## Planner components

Application điều phối các port:

- `GeocodingResolver`
- `RouteProvider`
- `CorridorStationRepository`
- `VehicleEnergyProfileRepository`
- `EnergyEstimator`
- `ChargingTimeCalculator`
- `TariffCalculator`
- `RouteOptimizer`
- `ConfidenceEvaluator`
- `TripPlanRepository`

Component trả typed value/outcome, không throw provider-specific error qua
boundary. `NO_FEASIBLE_ROUTE` là domain outcome hợp lệ. Thiếu critical source,
stale tariff hoặc provider outage là failure/warning riêng; không được biến
thành một plan “ước chừng”.

Mỗi result pin algorithm configuration, profile, provider request hash,
station/availability/tariff source revision, calculated time, freshness và
expiry. Confidence gồm expected/conservative range và limitation, không chỉ một
generic score.

## PostGIS và query safety

Spatial input validate longitude/latitude, CRS, precision, radius/corridor
ceiling và result limit. Query dùng GiST index, bounded corridor và deterministic
ordering; không load toàn bộ station vào memory. Query plan/latency được kiểm
trên volume fixture đại diện trước khi khóa SLO.

Station discovery chỉ expose approved public projection. Internal operational
identifier, maintenance note hoặc telemetry không được lọt qua mapper.

## Provider adapter

Routes/Places adapter bắt buộc:

- browser/server key tách riêng và key restriction;
- field mask allowlist theo operation;
- Autocomplete session token;
- timeout, retry hữu hạn với jitter, circuit breaker và quota budget;
- request coalescing chỉ khi privacy/scope tương thích;
- attribution và provider policy metadata;
- redacted structured telemetry.

Không persist/cache raw route, address, coordinate, polyline hoặc response nếu
chưa có explicit policy approval. Record/replay fixture phải được phép sử dụng,
đã sanitize và không chứa customer location.

## Privacy và persistence

Persistence mapper dùng allowlist:

- pseudonymize place reference bằng key từ secret manager;
- loại raw coordinate/address/polyline/provider response;
- lưu purpose, privacy classification, retention và expiry;
- từ chối unknown field trước repository;
- không để cache TTL vượt retention;
- hỗ trợ purge bounded batch và DSAR lineage.

Pseudonymization không phải anonymization. Key rotation cần migration plan;
metric/log không được dùng pseudonymous reference làm high-cardinality label.

## Failure behavior

| Tình huống | Outcome |
| --- | --- |
| Địa điểm mơ hồ | `AMBIGUOUS_LOCATION`, yêu cầu khách chọn lại |
| Không đủ profile/source | `INSUFFICIENT_DATA`, không tự điền |
| Critical data stale | `STALE_CRITICAL_DATA`, fail closed |
| Không có phương án giữ reserve | `NO_FEASIBLE_ROUTE` |
| Tariff không xác định | Plan có cost unknown hoặc `TARIFF_AMBIGUOUS` theo policy |
| Provider timeout/quota | Circuit breaker; approved fallback hoặc unavailable |
| Cancel/result đến muộn | Fencing loại result, plan giữ cancelled |
| Redis lỗi | Fallback source nếu an toàn; cache không là authority |
| PostGIS/source lỗi | Không trả plan cũ quá freshness |

## Kiểm thử bắt buộc

- Contract/state test cho `202`, poll, idempotency, OCC, cancel và fencing.
- Unit/property test cho SOC/reserve, consumption, curve/taper và tariff.
- Scenario test cho không sạc, một trạm, nhiều trạm và no-feasible-route.
- Connector, opening hour, timezone/DST, stale availability và tariff ambiguity.
- Provider field mask/key isolation, quota, timeout, malformed response và
  circuit breaker bằng adapter fake/record-replay.
- PostGIS query correctness, bounded result, index/query plan và load.
- Cross-subject denial, redacted log, persistence allowlist, expiry, purge và
  DSAR.
- Calibration metrics: SOC MAE, underprediction quantile, calibration error và
  reserve violation.

Public contract hoặc migration chạy full API/contract gate. Provider smoke test
thật phải có budget cap; không báo pass khi chỉ chạy fake adapter.
