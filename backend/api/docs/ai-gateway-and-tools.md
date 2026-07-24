---
id: api-ai-gateway-tools
title: AI Gateway và read-only tools của API Platform
status: active
owner_role: engineering-lead
scope: api
when_to_read:
  - customer-conversation
  - ai-client
  - ai-tool
  - ai-vision
  - local-inference
tags:
  - ai-gateway
  - tools
  - security
  - resilience
revision: 1
review_date: 2026-08-23
supersedes: []
---

# AI Gateway và read-only tools

## Signed assertion

API gửi FastAPI một assertion ngắn hạn, chống replay và pin:

- issuer, audience, request/correlation ID;
- subject pseudonym, assistant profile và granted scopes;
- conversation ID/version và cancellation/fencing ID;
- locale, data classification, token/cost budget;
- active policy, graph và knowledge revision được phép.

FastAPI không tin header từ client. Assertion không mang raw customer profile,
VIN, cookie, bearer token hoặc quyền rộng hơn request hiện tại.

## Semantic gateway

Edge thực hiện cheap validation trước AI: size/rate, locale, known abuse,
profile eligibility, obvious OOD và routing hint. Classifier/embedding chỉ là
defense/cost control, không là business authority. Competitor keyword không bị
chặn mù quáng; policy quyết định câu hỏi so sánh nào được trả lời bằng approved
evidence và câu nào phải deflect.

Threshold, model revision và latency được benchmark. Nếu classifier unavailable,
request không tự bypass security; API dùng safe policy route hoặc handoff.

## Vision upload

Endpoint yêu cầu `authenticated_customer`, object authorization và
`has_vehicle=true`. Ngoài RBAC, file phải qua allowlisted MIME/signature, size,
pixel/decompression limit, checksum, malware scan, metadata stripping và
quarantine. Derived OCR text vẫn là untrusted input và được gửi lại semantic
injection scan trước AI graph.

## Tool execution

AI chỉ trả `ToolProposal` theo registry/version và JSON Schema. API:

1. xác minh tool được phép cho profile/scope;
2. validate schema, business identifier và object authorization;
3. áp timeout, quota, idempotency/replay rule;
4. gọi owning application port/provider adapter;
5. chạy Tool Anomaly Gateway;
6. trả typed result với source revision/freshness.

V6 chỉ có read-only tools. Proposal side effect bị từ chối kể cả model/provider
đã sinh đúng JSON.

## Anomaly và micro-cache

Anomaly policy kiểm unit, currency, plausible range, effective date, revision,
cross-field invariant và conflict với active source. Giá, promotion, safety hoặc
legal conflict fail closed bằng typed error; model không được “sửa” dữ liệu.

Read-only dynamic result có thể cache 3–5 phút theo session/subject/market/scope
nếu Data Owner cho phép. Cache key pin source revision; revoke/DSAR/revision
invalidation phải xóa được. Không dùng global semantic cache cho customer data.

## Resilience và error mapping

Timeout/5xx đi qua circuit breaker; retry chỉ cho operation an toàn. AI provider
fallback nằm ở Model Mesh, không ở API controller. Nếu AI unavailable, API phát
customer-safe Static Handoff. Internal error được map sang stable reason code;
không lộ stack, prompt, provider secret hoặc raw tool payload.

Telemetry được enqueue non-blocking. Queue đầy áp sampling/drop policy đã duyệt
và metrics cảnh báo; không làm request chính thất bại.

## Kiểm thử bắt buộc

- Assertion replay, wrong audience/profile/scope và expired revision.
- Vision endpoint cho anonymous/không có xe, file spoof/bomb/malware và OCR injection.
- Tool schema, cross-subject, disabled tool, stale source và anomaly.
- Session cache isolation, invalidation và DSAR purge.
- Timeout/circuit breaker/static handoff và telemetry outage.
