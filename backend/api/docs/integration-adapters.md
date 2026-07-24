---
id: api-integration-adapters
title: Chuẩn tích hợp provider của API Platform
status: active
owner_role: engineering-lead
scope: api
when_to_read:
  - integration
  - provider-adapter
  - webhook
  - reconciliation
tags:
  - integration
  - resilience
  - security
revision: 1
review_date: 2026-08-23
supersedes: []
---

# Chuẩn tích hợp provider của API Platform

## Boundary và placement

Provider adapter nằm trong `infrastructure` của bounded context sở hữu use
case. Domain/application phụ thuộc port trung lập provider; controller không
gọi SDK hoặc endpoint bên ngoài trực tiếp. Không tạo top-level
`integrations`, module theo vendor hay một service mới chỉ để bọc SDK.

## Contract của adapter

Mỗi adapter khai báo input/output đã validate, timeout, retry eligibility,
idempotency, quota, error mapping, data classification, source revision và
freshness. Provider response được map sang type của application; raw payload,
secret và unredacted PII không đi vào domain, log hoặc durable projection.

## Resilience và failure behavior

- Retry có giới hạn chỉ áp dụng cho lỗi tạm thời và thao tác an toàn khi
  replay. Không retry vô hạn hoặc nhân đôi side effect.
- Circuit/disabled mode phải trả failure state rõ ràng. Fixture, cache stale
  hay model output không được giả làm provider authority.
- Mutation retryable dùng idempotency key. Thay đổi state và outbox event cùng
  transaction khi chúng thuộc một business action.
- Reconciliation ghi source revision, correlation ID, attempt/result và chứng cứ
  không chứa secret/PII. Dead-letter hoặc manual action cần owner và runbook.

## Inbound webhook

Xác minh signature, timestamp/audience, replay window và event identity trước khi
parse business payload. Persist receipt/idempotency trước side effect; unknown
event type fail closed. Webhook endpoint công khai không đồng nghĩa `@Public()`
không có provider authentication.

## Kiểm thử và evidence

Dùng deterministic fake hoặc record/replay đã redacted cho automated test; live
smoke test phải có budget cap và credential được phê duyệt. Kiểm thử success,
timeout, malformed response, quota, duplicate/replay, disabled mode và recovery.
Evidence ghi adapter revision, source/freshness, latency/error metrics, residual
risk và rollback; không ghi raw provider payload.

Chỉ tạo provider-specific runbook khi adapter và operator thực sự tồn tại.
