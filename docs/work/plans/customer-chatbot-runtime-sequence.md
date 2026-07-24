---
id: plan-customer-chatbot-runtime-sequence
title: ExecPlan Conversation Runtime, LangGraph và Knowledge foundation
status: active
owner_role: engineering-lead
scope: cross-system
when_to_read:
  - VFBIZ-0017
  - VFBIZ-0018
  - VFBIZ-0019
  - VFBIZ-0020
  - VFBIZ-0021
  - VFBIZ-0022
  - VFBIZ-0023
  - VFBIZ-0024
  - VFBIZ-0025
  - VFBIZ-0026
tags:
  - conversation
  - langgraph
  - knowledge
  - ingestion
revision: 1
review_date: 2026-08-23
supersedes: []
---

# Purpose

Đưa Customer Chatbot V6 từ account/vehicle foundation tới một Conversation
Runtime durable, LangGraph state machine và Knowledge foundation có kiểm soát.
Plan này chỉ điều phối dependency/integration; acceptance nằm trong work item.

## Scope và non-goals

Trong scope:

- NestJS Conversation Runtime core và persistence.
- Public/private conversation contracts.
- LangGraph dependency, protocol verifier và Conversation Graph.
- Knowledge Release control plane và approved knowledge-source ingestion.
- API–AI transport, active retriever và staging integration evidence.

Ngoài scope:

- Employee/CRM assistant.
- Side-effecting business tool.
- Vision upload, real model provider, production content crawl và SFT.
- Trip Planner hoặc mobile UI.

## Progress

- [x] VFBIZ-0017: Conversation Runtime application core.
- [ ] VFBIZ-0018: persistence/migration integration.
- [ ] VFBIZ-0019: public/private Conversation Turn Protocol.
- [ ] VFBIZ-0020: LangGraph dependency/private protocol foundation.
- [ ] VFBIZ-0021: LangGraph Conversation Graph.
- [ ] VFBIZ-0022: Knowledge Release control plane.
- [ ] VFBIZ-0023: approved knowledge-source ingestion.
- [ ] VFBIZ-0024: API–AI Conversation Transport integration.
- [ ] VFBIZ-0025: active retriever và Knowledge Release đầu tiên.
- [ ] VFBIZ-0026: staging integration và release evidence.

## Dependency và concurrency

```text
Account/Vehicle prerequisite:
0027 -> 0028 -> 0030
0027 -> 0029 -> 0032
0033 -> 0034

0017 API core
  + 0032 -> 0018 persistence
  + 0028 + 0030 -> 0019 public/private contract
  -> 0020 AI dependency/protocol
  -> 0021 LangGraph
  -> 0022 Knowledge Release
  -> 0023 source ingestion
  -> 0025 active retriever/release

0019 + 0021 -> 0024 API–AI transport
0024 + 0025 + 0033 + 0034 -> 0026 staging integration evidence
```

Không fan-out các item trên vì chúng kế thừa contract/revision tuần tự.
Parallelism chỉ dùng bên trong một phase cho explorer/reviewer read-only hoặc
sau khi integration owner tách writer path, claim và worktree rõ ràng. Migration,
contract, lockfile và knowledge registry luôn cần lease.

## Decisions

- Durable turn/state authority nằm ở API; LangGraph không sở hữu customer.
- Public API không stream hidden reasoning. Status event chỉ mô tả hành động hệ
  thống an toàn cho khách hàng.
- Internal protocol freeze trước LangGraph để NestJS/FastAPI không suy đoán.
- Knowledge Release và source ingestion tách nhau; ingestion không tự approve.
- Dataset Factory evaluation/red-team/training là workflow khác runtime
  knowledge ingestion.
- Foundation kết thúc ở 0023 chưa phải chatbot hoạt động. Transport/retriever/
  staging evidence thuộc 0024–0026 và vẫn fail closed cho tới khi hoàn tất.
- Account scope/session/DSAR và Vehicle Catalog/commercial fact gates được quản
  lý tại `account-vehicle-enterprise-hardening.md`; authenticated chat hoặc
  vehicle/price tool không được mở sớm hơn dependency tương ứng.

## Validation

- Mỗi work item chạy exact required checks và lưu observed evidence.
- Provider-neutral context scenario phải route cùng owner/docs/skill trên
  Codex, Claude, Gemini và generic bootstrap.
- Handoff checkpoint pin Git revision, source hashes và exact next action.
- Review/fix tối đa hai vòng; finding cũ cần evidence hash mới.

## Rollback và recovery

- Runtime có feature flag/disabled AI dispatch cho tới khi protocol/graph đạt.
- Migration dùng expand/backfill/contract và clean/legacy replay.
- Contract v1 chỉ additive; breaking change cần ADR/version mới.
- LangGraph checkpoint mismatch giữ validated Global Entities và reset
  Active Task; Knowledge activation dùng atomic pointer/rollback.
