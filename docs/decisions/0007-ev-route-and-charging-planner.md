---
id: adr-0007-ev-route-and-charging-planner
title: ADR 0007 — EV Route & Charging Planner
status: active
owner_role: architect
scope: cross-system
when_to_read:
  - ev-trip-planner
  - charging-station
  - maps-provider
  - mobility
  - architecture
tags:
  - adr
  - mobility
  - trip-planner
  - maps
revision: 1
review_date: 2026-10-24
supersedes: []
---

# ADR 0007 — EV Route & Charging Planner

## Status

Accepted cho kiến trúc đích. Quyết định này chưa cấp quyền production release
và không tuyên bố runtime đã được triển khai.

## Context

VFBiz cần một capability giúp khách hàng tìm trạm sạc và lập kế hoạch hành
trình EV dựa trên tuyến đường, mẫu xe, mức pin, charging curve, connector,
availability và tariff. Việc dùng LLM để tính quãng đường, năng lượng hoặc chi
phí không đáp ứng yêu cầu correctness. Việc gộp pre-trip planning với live
vehicle navigation, telemetry và safety-critical rerouting cũng tạo trust
boundary quá rộng cho giai đoạn đầu.

## Decision

1. Tên sản phẩm là **Lập kế hoạch hành trình EV**; technical capability là
   `ev-route-and-charging-planner`.
2. Baseline chỉ bao gồm Station Discovery và pre-trip planning. Live guidance,
   vehicle telemetry, in-drive rerouting và Federated Learning là chương trình
   safety-critical riêng trong tương lai.
3. NestJS Mobility context sở hữu public contract, input validation,
   authorization, provider orchestration và deterministic planning policy.
   Chỉ tách graph solver sang Go/Rust khi profiling chứng minh Node.js không
   đạt SLO đã được phê duyệt.
4. PostgreSQL/PostGIS giữ governed projection cho vehicle energy profile,
   charging location, EVSE, connector, tariff, availability và reliability.
   Redis chỉ cache dữ liệu nội bộ hoặc provider content được phép, theo revision
   và TTL.
5. Google Maps/Routes là provider tuyến đường qua adapter. V-GREEN/CSMS hoặc
   provider vận hành được phê duyệt mới là authority cho live station status,
   connector và tariff. Không tái sử dụng hoặc cache Google content trái điều
   khoản provider.
6. Planner tạo expected và conservative energy range, áp dụng reserve SOC,
   connector compatibility, charging curve, tariff window, freshness và
   reliability. Không có phương án an toàn phải trả typed
   `NO_FEASIBLE_ROUTE`, không tự hạ reserve hoặc bịa trạm.
7. Chatbot chỉ gọi planner bằng read-only tool đã đăng ký. LLM không tự tính
   route, năng lượng, thời gian sạc hoặc chi phí.
8. GCP-first nhưng provider nằm sau port/adapter. Kafka, custom Go router,
   TensorFlow.js edge predictor, local voice SLM và Federated Learning không
   thuộc baseline nếu chưa có benchmark, owner và consumer thực tế.

## Alternatives

- **LLM lập kế hoạch trực tiếp:** loại bỏ vì không deterministic và không có
  authority cho dữ liệu động.
- **Xây navigation engine thay Google ngay từ đầu:** loại bỏ vì chi phí, dữ liệu
  bản đồ và vận hành vượt phạm vi pre-trip baseline.
- **Kafka và telemetry xe trong release đầu:** trì hoãn vì chưa có vehicle
  identity, OEM gateway, consent, volume evidence và safety case.
- **Neo4j cho charging graph:** không chọn mặc định; graph tìm đường là runtime
  model, không đòi hỏi Knowledge Graph database khi PostGIS và cấu trúc dữ liệu
  hiện đáp ứng.

## Consequences

- Cần data model chuẩn Location → EVSE → Connector, versioned energy profile,
  tariff component và availability observation.
- Google/V-GREEN contracts, attribution, retention và caching policy cần
  Legal/Data Owner phê duyệt trước production.
- Accuracy được đánh giá bằng SOC error, underprediction quantile, calibration,
  reserve violation và route feasibility; không dùng tuyên bố “99% chính xác”.
- Mobile offline và live telemetry có thể kế thừa contract nhưng phải có ADR,
  threat model và safety release riêng.

## Verification

- Unit/property tests cho consumption, reserve, charging curve và tariff.
- Scenario tests: không cần sạc, một trạm, nhiều trạm, connector không tương
  thích, stale data, provider outage và không có tuyến khả thi.
- Mọi result pin algorithm, route provider, vehicle profile, station/tariff
  revision cùng freshness.
- Load benchmark khóa capacity/SLO trước production; không dùng con số giả định.

## Approval

Architecture decision owner: `architect`. Product scope, provider contract,
privacy, safety và production release vẫn cần named human approval tương ứng.
