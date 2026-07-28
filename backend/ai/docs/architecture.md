---
id: ai-architecture
title: Kiến trúc AI Platform
status: active
owner_role: engineering-lead
scope: ai
when_to_read:
  - ai-boundary
  - customer-chatbot
  - ai-tool
tags:
  - fastapi
  - architecture
  - rag
revision: 2026-07-27.1
review_date: 2026-08-23
supersedes: []
---

# Kiến trúc AI Platform

## Trust boundary

AI Platform chỉ nhận signed gateway assertion từ API Platform. Assertion pin
issuer, audience, subject, scope và assistant profile. Header do browser/mobile
tự gửi không cấp quyền. Liveness là route công khai duy nhất.

## Module responsibility

| Capability | Trạng thái |
|---|---|
| Signed API → AI boundary và LangGraph runtime | Implemented |
| Public released-knowledge retrieval | Candidate |
| Customer-private read-only tools | Target-only |
| Production assistant release | Human-blocked |

```text
assistant  -> LangGraph state, Supervisor, policy outcomes
knowledge  -> versioned evidence and ACL-aware retrieval
inference  -> governed model gateway, provider-neutral generation and citation draft
evaluation -> independent evidence
governance -> release state, kill switch and audit reference
```

`assistant` orchestration depends on provider-neutral `knowledge` and `inference`
ports. Provider SDKs remain in `app/infrastructure`; model or provider names do
not enter domain types. Tool proposal contract chỉ được materialize khi có
registry release và NestJS executor; AI không thực thi business side effect.

Chi tiết graph, revision, serving và release lần lượt nằm trong
`conversation-graph.md`, `knowledge-release.md`, `inference-serving.md` và
`evaluation-and-release.md`; không lặp lại trong tài liệu tổng quan này.

## Profile isolation

| Profile | Retrieval | Tool authority |
|---|---|---|
| public_customer | approved public namespace | read-only public tools |
| authenticated_customer | approved public namespace | scoped read proposal qua NestJS |

Profile không làm tăng quyền của signed assertion. Public RAG V1 cố ý
subject-agnostic và cấm private customer data. Cross-subject access chỉ xuất
hiện ở read-only business tool, nơi NestJS kiểm object authorization và fail
closed.

Owner/employee assistant là capability tương lai và phải có profile, namespace,
tool policy, evaluation suite cùng release riêng trước khi được thêm vào bảng.

## Runtime failure behavior

- Không có approved evidence thì refuse hoặc hand off trước provider call.
- Draft thiếu hoặc sai citation không được trở thành factual answer.
- Gateway assertion sai, profile escalation, cross-subject retrieval và provider
  failure đều fail closed.
- Tool proposal không cấp authority; API Platform xác thực, authorize, confirm,
  execute và audit.
The private execution boundary uses asymmetric authentication in both
directions: API assertions authenticate requests; short-lived Ed25519 detached
signatures authenticate successful AI response bytes and bind request plus
correlation identity. Private response keys are secret-mounted files, never
environment values. Production mTLS remains a separate deployment requirement.
