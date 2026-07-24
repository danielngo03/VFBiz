---
id: adr-0002-customer-chatbot-v6
title: ADR 0002 — Customer Chatbot V6
status: active
owner_role: architect
scope: cross-system
when_to_read:
  - customer-chatbot
  - architecture
  - ai-release
  - knowledge-revision
tags:
  - adr
  - chatbot
  - ai
revision: 2
review_date: 2026-08-23
supersedes:
  - adr-0001-staging-account-chat-trip
---

# ADR 0002 — Customer Chatbot V6

## Status

Accepted cho architecture foundation. Runtime production release vẫn cần
Security, Privacy, Data, Legal và Release Owner phê duyệt evidence tương ứng.

## Context

ADR 0001 gộp Account, Chatbot và Trip Planner vào một staging scope, khiến
ownership và context routing quá rộng. Chatbot doanh nghiệp cần stateful
orchestration, evidence freshness, durable handoff, model/runtime resilience và
Dataset Factory riêng, nhưng không được trao business authority cho model.

## Decision

1. Customer Chatbot V6 là kiến trúc AI đã chấp nhận. Thứ tự implementation hiện
   được ADR 0003 chuyển Account/Vehicle foundation lên trước Conversation Runtime;
   Trip Planner vẫn ở roadmap.
2. NestJS sở hữu public contract, identity/object authorization, conversation
   inbox/state projection, quota, handoff, tool execution và system integration.
3. FastAPI sở hữu private LangGraph State Machine, policy, retrieval, Vision
   observation, model routing, evaluation và tool proposal.
4. LangGraph dùng Global Entities + Active Task State, bounded self-correction
   và versioned checkpoint; không dùng linear pipeline hoặc unbounded agent loop.
5. Tool V6 là read-only. Live fact/calculation đến từ authorized tool/source,
   không đến từ model memory.
6. Local inference baseline là vLLM; TensorRT-LLM là optional deployment profile
   sau benchmark. Provider/model name không trở thành top-level domain module.
7. Critical knowledge publish dùng revision candidate và atomic activation;
   query trong sync barrier không được trộn revision.
8. Prompt/policy/graph/retriever/dataset/tool revision là release unit, qua
   golden, red-team, shadow, canary, rollback và kill switch.
9. Dataset Factory ưu tiên evaluation/red-team. Không download source thiếu
   approved rights và chưa tạo SFT release trong đợt đầu.

## Consequences

- API và AI cần contract nội bộ typed, cancellation/fencing và error taxonomy.
- Customer engagement, mobility, assistant orchestration, model platform,
  knowledge engineering, assurance và data governance có owner tách biệt.
- Chi phí tăng ở evaluation/shadow nhưng giảm rủi ro release và model/provider
  lock-in.
- Supervisor thông minh hơn router tĩnh nhưng mọi loop bị giới hạn, observable
  và không được nới authority.

## Rejected alternatives

- Một FastAPI public backend cho cả customer/API/AI: trộn trust boundary và
  transactional authority.
- Linear pipeline duy nhất: không đủ cho interrupt, clarification và stateful
  multi-turn.
- Microservice cho mỗi agent/model/dataset: tăng vận hành trước khi có nhu cầu.
- Fine-tune factual knowledge: gây stale fact và không giải quyết authorization.
- Cho LLM-as-a-Judge tự release dataset/model: vi phạm separation of duties.

## Verification

Quyết định chỉ được coi là implemented khi routing scenarios, dataset rights
gate, graph/state contract tests, provider failure, revision barrier,
cross-subject denial và release rollback có observed evidence.
