---
id: adr-0001-staging-account-chat-trip
title: Account, chatbot và Trip Planner trên staging
status: superseded
owner_role: architect
scope: cross-system
when_to_read:
  - identity
  - chatbot
  - trip
  - staging-mvp
tags:
  - adr
  - identity
  - ai
  - trip
revision: 2
review_date: 2026-08-22
supersedes: []
---

# ADR 0001: Account, chatbot và Trip Planner trên staging

> Quyết định này được ADR 0002 thay thế đối với current delivery focus. Các
> capability Account và Trip Planner không bị hủy; chúng quay lại roadmap để
> được quyết định bằng work item riêng.

Decision date: 2026-07-22

## Context

Sprint phải chứng minh một vertical slice staging có account, garage, grounded
chatbot và EV Trip Planner mà không biến Drupal thành transaction system, không
đưa AI ra public trực tiếp và không sử dụng production data.

## Decision

- Dùng hai Keycloak realm trên staging thông qua provider-neutral OIDC adapter:
  customer và workforce. API lưu opaque subject, không lưu credential/MFA secret.
- Client web dùng BFF session cookie; mobile tương lai dùng Authorization Code +
  PKCE. Customer và workforce audience/session không dùng chung.
- API Platform là public `/api/v1` duy nhất và giữ authorization, idempotency,
  audit, operational projections và provider orchestration.
- AI Platform là private service. RAG với citation/refusal được dùng trước;
  public và customer-scoped namespace tách biệt. Fine-tuning không thuộc sprint.
- Tool chỉ là proposal từ model; API xác thực, phân quyền, validate và thực thi.
  Sprint không có side-effecting AI tool.
- Trip Planner là deterministic domain service. Google Routes là provider qua
  port/adapter có quota, cache-policy, circuit breaker và record/replay test.
- PostgreSQL/PostGIS phục vụ API, PostgreSQL/pgvector riêng phục vụ AI, PostgreSQL
  riêng cho Keycloak, Redis cho cache/session/rate limit, MariaDB cho Drupal.
- Chỉ synthetic/versioned data trên staging; source, revision, effective date và
  freshness là bắt buộc cho facts động.

## Consequences

Staging có thể đổi CIAM/model/maps provider qua adapter. Đổi public contract,
migration, dataset registry hoặc trust boundary cần lease độc quyền và review.
Việc này chưa chứng minh production HA/DR, DMS/VIN verification hay payment.

## Rejected alternatives

- Drupal lưu customer/transaction/AI data: sai system boundary và tăng bề mặt PII.
- Model tự tính hành trình hoặc ghi dữ liệu: không deterministic và khó kiểm soát.
- Fine-tuning để “ghi nhớ” facts: không giải quyết freshness, citation hay ACL.
- Dùng chung realm/index cho customer và workforce: tăng nguy cơ privilege/ACL leak.
