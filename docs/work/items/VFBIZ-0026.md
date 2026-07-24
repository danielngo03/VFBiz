---
id: VFBIZ-0026
title: Customer Chatbot staging integration và release evidence
status: proposed
mode: controlled
priority: P0
owner_team: architecture-integration
accountable_role: release-owner
primary_workspace: root
affected_workspaces:
  - root
  - api
  - ai
allowed_paths:
  - tests/contract
  - tests/e2e
  - tests/performance
  - tests/resilience
depends_on:
  - VFBIZ-0024
  - VFBIZ-0025
  - VFBIZ-0033
  - VFBIZ-0034
  - VFBIZ-0035
  - VFBIZ-0037
  - VFBIZ-0038
controlled_signals:
  - ai-assistant
  - ai-retrieval
  - architecture
  - customer-conversation
  - ai-release
  - pii
exclusive_resources: []
required_checks:
  - npm run verify:governance
  - npm run verify:api
  - npm run verify:ai
revision: 1
review_date: "2026-08-23"
---

# Outcome

Staging chứng minh public/authenticated Customer Chatbot đi xuyên API–AI–active
knowledge bằng cùng contract, có citation/refusal/handoff và failure behavior
quan sát được; work item chỉ tạo evidence, không tự phát hành production.

## Constraints

- Không sửa runtime để làm test “xanh”; finding quay về đúng owner work item.
- Không dùng production PII, customer conversation hoặc unapproved VinFast fact.
- Test không yêu cầu chain-of-thought và không ghi secret/token vào artifact.
- Production release vẫn cần human Release/Security/Privacy/Data authority.

## Done when

- Contract/E2E bao phủ public và authenticated subject isolation.
- Citation/refusal, knowledge updating, provider outage, cancel/reconnect và
  offline handoff đạt.
- Load/cost/security suite dùng record/replay theo budget; smoke provider thật
  chỉ chạy khi có explicit approval.
- Release manifest pin contract, graph, policy, model, embedding, knowledge và
  test evidence revision.
- Residual risk, rollback và kill switch được review; không critical/high mở.

## Checkpoint

- Exact next action: chỉ start khi VFBIZ-0024 và VFBIZ-0025 `done`; integration
  owner tạo context/claim riêng cho root test paths.

## Evidence

- [ ] `npm run verify:governance` — add evidence reference
- [ ] `npm run verify:api` — add evidence reference
- [ ] `npm run verify:ai` — add evidence reference
