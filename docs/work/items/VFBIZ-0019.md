---
id: VFBIZ-0019
title: Conversation Turn Protocol và public contract v1
status: proposed
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
revision: 1
review_date: "2026-08-23"
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
- Assertion pin request/correlation/conversation/version/fencing/profile/scope/
  locale/budget/policy/graph/knowledge revision, expiry và replay ID.
- Public OpenAPI phản ánh durable turn/event/cursor thay vì hứa synchronous
  answer khi AI chưa sẵn sàng.
- Breaking change bị compatibility gate từ chối; SDK regenerate/typecheck đạt.

## Checkpoint

- Exact next action: freeze vocabulary sau VFBIZ-0018 và chạy contract examples
  ở cả NestJS lẫn FastAPI trước khi thêm LangGraph dependency.

## Evidence

- [ ] `npm run contracts:lint` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
