---
id: VFBIZ-0019
title: Conversation Turn Protocol và public contract v1
status: done
mode: controlled
priority: P0
owner_team: architecture-integration
accountable_role: architect
primary_workspace: root
affected_workspaces:
  - root
  - api
  - ai
allowed_paths:
  - contracts/openapi
  - contracts/ai
  - packages/api-client/src/generated.ts
  - docs/architecture
  - docs/decisions
depends_on:
  - VFBIZ-0018
  - VFBIZ-0028
  - VFBIZ-0030
controlled_signals:
  - customer-conversation
  - public-contract
  - architecture
  - ai-assistant
  - authorization
  - pii
exclusive_resources:
  - public-contract
required_checks:
  - npm run contracts:lint
  - npm run governance:check
revision: 8
review_date: "2026-08-23"
updated_at: "2026-07-24T18:34:39.663Z"
---

# Outcome

Public Conversation API và private API–AI Conversation Turn Protocol v1 có
machine-readable contract thống nhất để NestJS/FastAPI triển khai độc lập mà
không suy đoán field, authority hoặc failure state.

## Constraints

- Contract-first; lane này không triển khai model, RAG hay business tool.
- Private assertion phải được ký, expire nhanh và pin authorization/budget/
  revision/fencing; AI không tin customer ID do client tự gửi.
- V1 chỉ chấp nhận `public_customer` và `authenticated_customer`.
- Public stream chỉ có customer-safe status, citation, answer, handoff và error;
  không có chain-of-thought.

## Done when

- JSON Schema định nghĩa request/result/event/error/cancel và signed assertion.
- Public contract có create/get/close session, enqueue message, list message,
  cancel turn, handoff và SSE event stream; message command trả `202`.
- Event envelope pin `eventId`, `schemaVersion`, session/turn ID, monotonic
  sequence, timestamp, correlation ID và typed data.
- SSE contract định nghĩa `Last-Event-ID`, heartbeat, retention, reconnect,
  duplicate cursor và backpressure; không dùng stream làm source of truth.
- Assertion pin request/correlation/conversation/version/fencing/profile/scope/
  locale/budget/policy/graph/knowledge revision, expiry và replay ID.
- Public OpenAPI phản ánh durable turn/event/cursor thay vì hứa synchronous
  answer khi AI chưa sẵn sàng.
- Breaking change bị compatibility gate từ chối; SDK regenerate/typecheck đạt.

## Checkpoint

- Contract vocabulary đã freeze. Exact next action sau khi đóng work item:
  VFBIZ-0020 triển khai private API assertion/checkpoint boundary mà không
  kích hoạt candidate public operations.

## Evidence

- [x] `npm run contracts:lint` — PASS; candidate Conversation OpenAPI được lint
  riêng, sáu runtime schemas compile strict và released SDK không chứa tám
  candidate operation.
- [x] `npm run governance:check` — PASS; docs, reports, authorization, work-item
  schemas, instruction budgets và 61 context scenarios đạt.

### Additional observed evidence

- `npm run typecheck --workspace @vfbiz/api-client` — PASS sau regenerate; SDK
  phát hành không lộ candidate Conversation API.
- TypeScript compile fixture — PASS cho toàn bộ durable/transient event và
  exhaustive `switch(frame.type)` không dùng cast.
- AJV semantic examples — PASS; factual `answered` thiếu citation và
  `answer.delta` đều bị từ chối.
- Independent review cycle 2 — không còn P0; bốn P1 cuối đã được đóng bằng
  discriminated event union, candidate-spec isolation, validated-final-only
  answer delivery và loại bỏ legacy `/internal/v1/answers` khỏi contract.

### review — 2026-07-24T18:34:39.377Z

Two bounded independent review cycles completed; final P1 findings are resolved and all required gates pass.

### done — 2026-07-24T18:34:39.663Z

Conversation protocol v1 is frozen as an isolated candidate contract; released SDK remains unchanged until runtime cutover.
