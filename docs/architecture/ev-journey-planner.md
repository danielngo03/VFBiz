---
id: ev-journey-planner-architecture
title: Kiến trúc EV Journey Planner
status: active
owner_role: architect
scope: cross-system
when_to_read:
  - ev-trip-planner
  - charging-data
  - route-provider
  - energy-model
  - location-privacy
  - trip-correctness
  - cross-system
context_anchors:
  ev-trip-planner: "## Boundary và authority"
  charging-data: "## Data model và interoperability"
  route-provider: "## Provider và cache governance"
  energy-model: "## Deterministic planner"
  location-privacy: "## Location privacy và retention"
  trip-correctness: "## Verification matrix"
  cross-system: "## Boundary và authority"
tags:
  - architecture
  - mobility
  - postgis
  - provider-governance
revision: 1
review_date: 2026-10-24
supersedes: []
---

# Kiến trúc EV Journey Planner

## Boundary và authority

Client chỉ gọi public API của NestJS. Mobility context sở hữu trip command,
object authorization, deterministic planning policy, provider orchestration,
persistence và public failure contract. Customer AI Assistant chỉ gọi
`plan_ev_trip` qua Tool Gateway; FastAPI/LLM không tính route, SOC, charging
time hoặc tariff.

```text
Customer Portal / Mobile / Chatbot tool
                    |
              NestJS Mobility
     +--------------+---------------+
     |              |               |
 Route ports   Planner core    Trip persistence
     |              |               |
 Google       PostGIS/energy   API PostgreSQL
 adapters     charging data    minimized projection
```

V-GREEN/CSMS projection là authority cho vận hành trạm, connector, availability
và tariff. Google Maps/Routes là route/place provider, không trở thành
System-of-Record cho charging data. OCPP nằm giữa CSMS và charger; public
Customer API không kết nối trực tiếp với OCPP endpoint.

## Public asynchronous contract

```text
GET  /api/v1/trip/vehicle-profiles
GET  /api/v1/charging/locations
GET  /api/v1/charging/locations/{locationId}
POST /api/v1/trip/plans
GET  /api/v1/trip/plans/{planId}
POST /api/v1/trip/plans/{planId}/cancel
```

`POST /trip/plans` validate request, reserve idempotency, persist job và trả
`202 Accepted`. `GET` trả projection bền vững; client không phụ thuộc kết nối
HTTP dài hoặc provider callback.

```text
queued -> routing -> evaluating_stops -> completed
   |          |              |
   +----------+--------------+-> failed
   +---------------------------> cancelled
```

Transition dùng OCC. Worker claim job bằng lease và fencing token; output từ
lease cũ không được commit. Cancellation là best-effort tới provider nhưng
fencing luôn chặn kết quả muộn. Repeated request dùng `Idempotency-Key` và
request fingerprint, không tạo plan trùng.

Mọi failure được map sang typed Problem Details hoặc plan failure code, gồm
`NO_FEASIBLE_ROUTE`, `INSUFFICIENT_DATA`, `STALE_CRITICAL_DATA`,
`ROUTE_PROVIDER_UNAVAILABLE`, `AMBIGUOUS_LOCATION`, `TARIFF_AMBIGUOUS`,
`CANCELLED` và `PLAN_EXPIRED`.

## Data model và interoperability

```text
VehicleEnergyProfileRevision
ChargingLocation
└── ChargingEVSE
    └── ChargingConnector
ChargingAvailabilityObservation
ChargingTariffRevision
└── TariffElement
    └── PriceComponent
ChargingReliabilitySnapshot
TripPlan
└── TripPlanAlternative
    ├── TripLeg
    └── ChargingStop
```

OCPI được dùng làm interoperability reference:

- `Location` mô tả site và thuộc tính tiếp cận.
- `EVSE` là một điểm có thể phục vụ một xe tại một thời điểm.
- `Connector` mô tả standard, format, power và capability vật lý.
- `Tariff` gồm nhiều element/component với restriction và effective window.

Không dùng `unitCount` để thay thế EVSE thực. Availability là observation có
`observedAt`, source và quality; không ghi đè thuộc tính tĩnh của Connector.
Tariff là revision, không sửa record lịch sử. Internal domain không lệ thuộc
trực tiếp DTO OCPI; adapter map external version sang canonical model.

## Deterministic planner

Planner là các component có port rõ ràng:

1. `GeocodingResolver` phát hiện địa điểm mơ hồ và chuẩn hóa reference.
2. `RouteProvider` lấy route candidate với field mask allowlist.
3. `CorridorStationQuery` dùng PostGIS tìm EVSE tương thích quanh route.
4. `EnergyEstimator` tính expected/conservative energy theo leg.
5. `ChargingTimeCalculator` áp charging curve, station power và taper.
6. `TariffCalculator` áp element, restriction, tax, parking và timezone.
7. `ConstrainedRouteOptimizer` tối ưu time/cost/reliability nhưng giữ reserve.
8. `ConfidenceEvaluator` đánh giá uncertainty, freshness và calibration.

Energy input có thể gồm usable capacity/degradation, consumption coefficients,
temperature, wind, elevation, traffic, HVAC và payload khi source/model hỗ trợ.
Thiếu input không được thay bằng con số model bịa ra; component áp approved
default có provenance hoặc tăng uncertainty/warning.

Optimizer không tự hạ reserve SOC, bỏ qua connector incompatibility hoặc dùng
station đóng cửa. Nếu không có phương án thỏa constraint, output duy nhất hợp
lệ là `NO_FEASIBLE_ROUTE` cùng lý do an toàn để UI hướng dẫn khách.

## Provider và cache governance

- Browser/server key, project, quota và credential được tách riêng.
- Places Autocomplete dùng session token; server không dùng browser key.
- Routes adapter có field mask allowlist theo use case, request coalescing,
  timeout, retry hữu hạn, circuit breaker và cost attribution.
- API key bị restrict theo API và referrer/IP thích hợp; secret không vào
  client bundle, log hoặc fixture.
- Attribution, terms và privacy notice theo provider được giữ ở UI/release.
- Raw Google route, coordinate, address, polyline và response không được persist
  hoặc cache trừ khi Data/Legal Owner xác nhận điều khoản cho phép.
- Place ID và derived/internal data chỉ cache theo documented provider policy.
- Redis cache key pin market, provider, policy và source revision; cache miss
  không được làm thay đổi correctness.
- Load test dùng approved record/replay fixture; smoke provider thật có quota và
  budget cap.

Provider SDK chỉ xuất hiện trong infrastructure adapter. Domain/application
không chứa tên Google, V-GREEN hoặc OCPI version trong business invariant.

## Location privacy và retention

Raw location là dữ liệu không tin cậy và có thể nhạy cảm:

- validate range, precision, CRS và request size trước spatial query;
- không ghi address/coordinate/polyline trong log, metric label hoặc audit;
- persist pseudonymous place reference và allowlisted summary khi có purpose;
- exact location, active job và cache có TTL riêng, không vượt retention;
- analytics chỉ nhận tile/geohash đã giảm precision theo privacy policy;
- key pseudonymization nằm trong secret manager và có rotation/migration plan;
- DSAR xóa plan, cache reference và derived analytics có subject lineage, trừ
  legal hold đã được phê duyệt.

Public station discovery không được dùng làm đường vòng để enumerate private
customer trip hoặc operational detail không dành cho public.

## Correctness, resilience và observability

Mỗi result pin:

- algorithm và configuration revision;
- vehicle energy profile revision;
- route provider/version và request hash;
- station, availability, reliability và tariff revisions;
- environmental source/revision khi được sử dụng;
- calculated time, freshness và expiry.

Telemetry ghi latency, provider cost, feasible outcome, stale-data block và
error class nhưng không ghi location/cardinality cao. Observability chạy ngoài
transaction chính; outage không làm plan sai hoặc làm lộ raw payload.

Circuit breaker chỉ chuyển sang adapter được phê duyệt có contract tương đương.
Không có safe provider/data thì fail closed. Redis lỗi fallback về source phù
hợp; PostgreSQL/PostGIS hoặc critical data authority lỗi thì không trả cached
plan quá freshness.

## Release và mở rộng

Baseline giữ planner trong NestJS modular monolith. Chỉ tách solver sang Go/Rust
khi profiling chứng minh runtime hiện tại không đạt SLO và có contract,
ownership, observability cùng rollback cho service mới.

Live navigation, telemetry xe, in-drive rerouting, booking/payment, prediction
availability, edge inference và Federated Learning cần chương trình riêng có
safety case. Schema và event baseline có thể mở rộng nhưng không tuyên bố các
capability tương lai đã được hỗ trợ.

## Verification matrix

| Area | Evidence tối thiểu |
| --- | --- |
| Energy | Unit/property tests cho SOC, reserve, consumption và uncertainty |
| Charging | Charging curve, taper, EVSE/connector compatibility và power cap |
| Tariff | Component, effective window, timezone/DST, currency, tax và ambiguity |
| Routing | Không sạc, một/multi stop, waypoint và no-feasible-route |
| Data | Stale observation, station closed, missing source và atomic revision |
| Provider | Field mask, key isolation, quota, timeout, malformed response và circuit breaker |
| Privacy | Redacted logs, pseudonymization, TTL, cross-subject denial và DSAR |
| Performance | Step-load bằng record/replay; smoke provider thật có budget cap |
| Calibration | SOC MAE, underprediction quantile, calibration và reserve violation |

Release đi qua offline evaluation, internal staging, shadow, canary theo market
và production ramp. SLO/capacity chỉ được khóa sau benchmark và human approval.
