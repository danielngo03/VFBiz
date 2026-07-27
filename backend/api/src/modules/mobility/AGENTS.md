# Mobility Platform

## Ownership

- Sở hữu Station Discovery, pre-trip planning, energy/charging policy,
  PostGIS query và provider orchestration phía NestJS.
- Không sở hữu Product catalog, Customer Garage, chatbot/LangGraph, OCPP charger
  session, live navigation hoặc vehicle telemetry.

## Invariants

- Planner deterministic; LLM không tính route, SOC, charging time hoặc cost.
- Charging model là `Location → EVSE → Connector`; không dùng `unitCount` thay
  EVSE hoặc suy diễn dữ liệu nguồn còn thiếu.
- Reserve SOC, connector compatibility, freshness và tariff window không được
  tự nới lỏng để tạo plan khả thi.
- Raw address, coordinate, polyline và provider payload không vào log hoặc
  persistence; location projection có purpose, pseudonymization và retention.
- Provider SDK chỉ nằm trong infrastructure adapter. Domain không import
  NestJS, Prisma hoặc vendor type.
- Plan job dùng idempotency, OCC, lease/fencing và typed terminal state.

## Read when applicable

- Product outcome: `docs/product/ev-journey-planner.md`
- Cross-system boundary: `docs/architecture/ev-journey-planner.md`
- Local implementation: `backend/api/docs/trip-engine.md`

## Verification

Chạy focused unit/integration test rồi `npm run verify:api`. Public contract,
schema/migration, route provider, location data, algorithm hoặc release là
controlled signal; dùng `validate-trip-release` và đúng risk/release reviewer.
