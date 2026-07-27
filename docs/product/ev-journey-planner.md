---
id: ev-journey-planner-product
title: Lập kế hoạch hành trình EV
status: active
owner_role: product-owner
scope: cross-system
when_to_read:
  - ev-trip-planner
  - charging-station
  - charging-data
  - customer-journey
  - mobility
context_anchors:
  ev-trip-planner: "## Bài toán sản phẩm"
  charging-station: "## Capability baseline"
  charging-data: "## Output và cách trình bày"
  customer-journey: "## Audience và hành trình chính"
  mobility: "## Bài toán sản phẩm"
tags:
  - product
  - mobility
  - charging
  - trip-planner
revision: 1
review_date: 2026-10-24
supersedes: []
---

# Lập kế hoạch hành trình EV

## Bài toán sản phẩm

Khách hàng cần biết một hành trình có khả thi với xe và mức pin hiện tại hay
không, nên dừng sạc ở đâu, mất bao lâu và chi phí ước tính là bao nhiêu. Những
thông tin này phải dựa trên dữ liệu xe, trạm, connector, tariff và tuyến đường
có nguồn rõ ràng; không được để LLM tự tính hoặc điền giá trị còn thiếu.

**Lập kế hoạch hành trình EV** là công cụ hỗ trợ quyết định trước chuyến đi,
không phải hệ thống dẫn đường đang chạy trên xe. Kết quả là một estimate có
uncertainty và freshness, không phải cam kết về mức pin, thời gian đến hoặc trạm
sạc chắc chắn còn trống.

## Audience và hành trình chính

| Audience | Hành trình | Ranh giới |
| --- | --- | --- |
| Khách public | Tìm trạm sạc và xem thông tin public được phê duyệt | Không đọc Garage hoặc lịch sử hành trình |
| Khách đã đăng nhập | Chọn xe trong Garage hoặc energy profile được duyệt, tạo và xem plan của chính mình | Không truy cập plan, vị trí hoặc Garage của khách khác |
| Nhân sự vận hành | Theo dõi freshness, anomaly và release của dữ liệu trạm/tariff theo capability | Không tự phê duyệt release do chính mình tạo |
| Customer AI Assistant | Tích hợp `plan_ev_trip` ở release sau baseline, sau evaluation và tool-registration gate | V1 không đăng ký tool; model không tự tính route, SOC, thời gian sạc hoặc chi phí |

## Capability baseline

- Tìm Charging Location theo vị trí, corridor và connector tương thích.
- Lập kế hoạch với điểm đi, điểm đến, waypoint tùy chọn, vehicle profile, SOC
  hiện tại, reserve SOC và preference.
- Trả nhiều phương án khi có ý nghĩa, ví dụ cân bằng, nhanh hơn hoặc chi phí
  thấp hơn.
- Ước tính distance, duration, energy range, SOC từng leg, charging stop,
  charging duration và cost.
- Hiển thị source revision, observed time, confidence và warning của dữ liệu.
- Xử lý plan bất đồng bộ, cho phép poll/cancel và không mất kết quả khi client
  mất kết nối.
- Refuse bằng typed outcome khi không có tuyến khả thi hoặc dữ liệu không đủ
  tin cậy; không tự hạ reserve SOC.

## Ngoài phạm vi baseline

- Không live navigation, turn-by-turn guidance hoặc safety-critical rerouting.
- Không nhận vehicle telemetry thời gian thực hoặc điều khiển phương tiện.
- Không giữ chỗ trạm, thanh toán, đặt dịch vụ hoặc tạo side effect thương mại.
- Không dự báo chính xác số trụ trống trong tương lai khi chưa có model và
  evidence được phê duyệt.
- Không Federated Learning, edge model, custom Go/Rust router hoặc Kafka chỉ để
  chuẩn bị cho quy mô chưa được benchmark.
- Không cache hoặc tái sử dụng Google Maps content ngoài quyền được provider
  cho phép.

Các capability này cần ADR, threat model và release gate riêng trước khi được
đưa vào roadmap thực thi.

## Input tối thiểu

- Origin, destination và waypoint tùy chọn ở dạng provider-neutral place
  reference; raw coordinate chỉ tồn tại ngắn hạn khi thật sự cần tính toán.
- Vehicle energy profile revision hoặc xe trong Garage đã resolve sang profile.
- Departure SOC và reserve SOC.
- Departure time và timezone.
- Preference: `balanced`, `fastest` hoặc `lowest_cost`.
- Tùy chọn đã được model hỗ trợ: hành khách/tải trọng, HVAC và accessibility.

Input thiếu, mơ hồ hoặc ngoài range tạo validation/clarification state; planner
không tự suy ra địa chỉ nhà, nơi làm việc, mức pin hoặc loại xe.

## Output và cách trình bày

Mỗi `TripPlan` có một hoặc nhiều alternative. Mỗi alternative phải cung cấp:

- distance, drive duration, charging duration và total duration;
- expected và conservative energy range;
- departure/arrival SOC cho từng leg;
- Charging Location, EVSE và Connector được chọn;
- arrival SOC, target SOC, charge duration và cost estimate tại từng stop;
- currency, tariff components và effective window đã dùng;
- vehicle, route provider, station, tariff, weather/elevation và algorithm
  revision liên quan;
- freshness, confidence và warning có thể hành động.

UI không dùng một con số duy nhất để che giấu uncertainty. Khi availability,
tariff hoặc environmental data stale, kết quả phải phân biệt rõ estimate,
last-known-good và unknown.

## Privacy và trust

Origin, destination, waypoint và route có thể tiết lộ nhà ở, nơi làm việc,
thói quen hoặc vị trí nhạy cảm. Vì vậy:

1. Không ghi raw address, coordinate, polyline hoặc provider payload vào log,
   audit và analytics.
2. Chỉ persist allowlisted projection đã pseudonymize, có purpose và retention.
3. Exact location có TTL ngắn; analytics dùng dữ liệu đã giảm độ chính xác.
4. Không suy diễn home/work hoặc tạo customer segment nếu chưa có consent và
   lawful purpose riêng.
5. Customer chỉ đọc/cancel plan thuộc đúng subject hoặc capability session.

## Product acceptance

- Luồng không cần sạc, một trạm, nhiều trạm và không có tuyến khả thi đều cho
  kết quả deterministic.
- Connector incompatibility, station closed, stale availability, tariff mơ hồ
  và provider outage có failure/warning rõ ràng.
- Không có cross-customer plan hoặc location leakage trong security suite.
- Property tests giữ reserve SOC và các invariant charging curve/tariff.
- Kết quả pin source, freshness, algorithm và provider revision.
- Record/replay load test không gọi provider tính phí; smoke test thật có budget
  cap và attribution đúng.
- Product/Release Owner chỉ khóa SLO và accuracy threshold sau benchmark.

## KPI

- Tỷ lệ tìm được phương án khả thi và tỷ lệ khách chọn một alternative.
- Sai số SOC, conservative underprediction và reserve violation.
- Tỷ lệ stale/unknown station hoặc tariff và lỗi provider.
- P50/P95 time-to-plan, cancellation completion và cost trên plan.
- Tỷ lệ plan phải tính lại, abandon và feedback về charging stop.

Không tối ưu KPI bằng cách loại bỏ warning, giảm reserve hoặc trình bày estimate
như dữ liệu live chắc chắn.
