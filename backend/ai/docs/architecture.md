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
revision: 2026-07-23.2
review_date: 2026-08-23
supersedes: []
---

# Kiến trúc AI Platform

## Trust boundary

AI Platform chỉ nhận signed gateway assertion từ API Platform. Assertion pin
issuer, audience, subject, scope và assistant profile. Header do browser/mobile
tự gửi không cấp quyền. Liveness là route công khai duy nhất.

## Module responsibility

```text
assistant  -> LangGraph state, Supervisor, policy outcomes
knowledge  -> versioned evidence and ACL-aware retrieval
inference  -> Model Mesh, provider-neutral generation and citation draft
tooling    -> typed read-only proposal
evaluation -> independent evidence
governance -> release state, kill switch and audit reference
```

`assistant` orchestration depends on provider-neutral `knowledge` and `inference`
ports. Provider SDKs remain in `app/infrastructure`; model or provider names do
not enter domain types. `tooling` emits a typed proposal and never executes a
business side effect.

Chi tiết graph, revision, serving và release lần lượt nằm trong
`conversation-graph.md`, `knowledge-release.md`, `inference-serving.md` và
`evaluation-and-release.md`; không lặp lại trong tài liệu tổng quan này.

## Profile isolation

| Profile | Retrieval | Tool authority |
|---|---|---|
| public_customer | approved public namespace | read-only public tools |
| authenticated_customer | subject-scoped namespace + approved public | scoped read proposal |

Profile không làm tăng quyền của signed assertion. Cross-profile access và
cross-subject retrieval phải fail closed.

Owner/employee assistant là capability tương lai và phải có profile, namespace,
tool policy, evaluation suite cùng release riêng trước khi được thêm vào bảng.

## Runtime failure behavior

- Không có approved evidence thì refuse hoặc hand off trước provider call.
- Draft thiếu hoặc sai citation không được trở thành factual answer.
- Gateway assertion sai, profile escalation, cross-subject retrieval và provider
  failure đều fail closed.
- Tool proposal không cấp authority; API Platform xác thực, authorize, confirm,
  execute và audit.
