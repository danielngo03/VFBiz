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
revision: 3
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

Transport nội bộ dùng contract `internal-v1` và chỉ chấp nhận EdDSA hoặc ES256.
Mỗi retry tạo `jti` và chữ ký mới vì replay store của AI tiêu thụ assertion
theo đúng một lần. Request hash bind method, exact path và canonical JSON;
response vượt 128 KiB, sai schema, factual answer không có citation hoặc tool
ngoài signed allowlist đều bị từ chối trước business commit.

Public key được API phát tại `/api/v1/internal/ai/jwks`; endpoint không nằm
trong customer/workforce OpenAPI và production ingress chỉ cho AI workload truy
cập. Private key luôn ở secret-mounted absolute path. Khi trust bị tắt, signer,
JWKS và transport đều fail closed nhưng baseline API vẫn khởi động được.

Trust/JWKS và execution dispatch dùng hai cờ riêng. Trust có thể được bật để
kiểm key rotation; dispatcher chỉ claim inbox khi graph handler, retrieval
snapshot và response-revision contract đã đạt staging gate. Mọi response phải
trả exact graph, policy và knowledge revision bundle khớp assertion. Citation
phải khai knowledge revision đã dùng; mismatch bị coi là stale execution và
không được commit.

## Semantic gateway

Edge thực hiện cheap validation trước AI: size/rate, locale, known abuse,
profile eligibility, obvious OOD và routing hint. Classifier/embedding chỉ là
defense/cost control, không là business authority. Competitor keyword không bị
chặn mù quáng; policy quyết định câu hỏi so sánh nào được trả lời bằng approved
evidence và câu nào phải deflect.

Threshold, model revision và latency được benchmark. Nếu classifier unavailable,
request không tự bypass security; API dùng safe policy route hoặc handoff.

## Vision upload sau baseline

Vision không thuộc text baseline. Khi capability được mở bằng release riêng,
endpoint yêu cầu `authenticated_customer`, object authorization và verified
vehicle association. Ngoài RBAC, file phải qua allowlisted MIME/signature, size,
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

Baseline chỉ có read-only tools. Proposal side effect bị từ chối kể cả
model/provider đã sinh đúng JSON. `HandoffRecommendation` là một AI outcome,
không phải `ToolProposal`: API kiểm customer scope, policy, consent và queue
state rồi mới tạo durable support handoff. Model không được phát sự kiện
`handoff.connected` hoặc tuyên bố đã chuyển nhân viên.

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

Retry budget tối đa hai lần và mỗi attempt vẫn phải nằm trong signed deadline.
Cancellation dùng endpoint riêng của turn và AbortSignal chỉ là best-effort;
conversation version cùng fencing token mới là hàng rào cuối cùng chống output
đến muộn. Circuit breaker hiện là per API replica; deployment phải kết hợp
upstream health/routing thay vì coi Redis là authority của breaker.

Telemetry được enqueue non-blocking. Queue đầy áp sampling/drop policy đã duyệt
và metrics cảnh báo; không làm request chính thất bại.

## Kiểm thử bắt buộc

- Assertion replay, wrong audience/profile/scope và expired revision.
- Vision endpoint cho anonymous/không có xe, file spoof/bomb/malware và OCR injection.
- Tool schema, cross-subject, disabled tool, stale source và anomaly.
- Session cache isolation, invalidation và DSAR purge.
- Timeout/circuit breaker/static handoff và telemetry outage.
Successful execution responses are authenticated independently from request
assertions. FastAPI signs the raw response digest with a short-lived Ed25519
workload key and binds it to request/correlation identity. NestJS holds only an
allowlisted public-key ring, verifies before JSON parsing, and fails closed on
missing, expired, unknown-key or tampered responses. Overlapping public keys
support rotation. This complements, but does not replace, production mTLS.
