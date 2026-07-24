---
id: customer-chatbot-v6-architecture
title: Kiến trúc Customer Chatbot V6
status: active
owner_role: architect
scope: cross-system
when_to_read:
  - customer-chatbot
  - customer-conversation
  - support-handoff
  - ai-vision
  - multimodal-injection
  - knowledge-revision
  - local-inference
  - cross-system
tags:
  - architecture
  - chatbot
  - ai
  - resilience
revision: 1
review_date: 2026-08-23
supersedes:
  - staging-mvp-boundaries
  - backend-platform-rebuild
---

# Kiến trúc Customer Chatbot V6

## Bảy lớp và trust boundary

```text
1. Drupal / Customer Portal / client
2. NestJS Edge, identity, quota, inbox và semantic gateway
3. Conversation state, handoff và durable event
4. FastAPI LangGraph Supervisor và policy
5. RAG, read-only tool proposal, Vision observation và anomaly gateway
6. Model Mesh, local/cloud inference, cache và provider fallback
7. Evaluation, PromptOps, audit, telemetry, Dataset Factory và release
```

Client chỉ gọi NestJS. FastAPI là private service và chỉ nhận signed assertion
pin issuer, audience, subject, profile, scopes, request budget và correlation ID.
FastAPI không đọc API PostgreSQL; NestJS không đọc AI PostgreSQL/pgvector.
Tool side effect bị cấm trong V6.

## Luồng dữ liệu chính

```text
message
  -> API validate identity/object scope/size/quota/sequence
  -> low-cost policy and semantic classification
  -> session inbox + OCC
  -> signed request to AI
  -> LangGraph Supervisor
  -> retrieval / read-only tool proposal / clarification / refusal / handoff
  -> citation and output policy
  -> durable event + client status/answer
```

Semantic gateway ở Edge được dùng để chặn abuse rõ ràng, kiểm kích thước, policy
và route chi phí thấp. Nó không được biến competitor keyword thành lệnh cấm mù
quáng hoặc hứa latency 20 ms không có benchmark. Các câu so sánh hợp lệ vẫn có
thể được xử lý bằng approved policy/evidence; safety-sensitive hoặc ambiguity
được chuyển tới graph.

## State Machine và self-correction

`ConversationGraphState` tách:

- `GlobalEntities`: thực thể đã xác nhận trong session như model xe, locale và
  profile; mỗi field có source, confidence, timestamp và sensitivity.
- `ActiveTaskState`: intent, required slots, tool attempt, cancellation token,
  current evidence và retry counter của tác vụ đang chạy.
- `ControlState`: graph version, policy revision, knowledge revision, token
  budget và event sequence.

Supervisor định tuyến động và nhận typed outcome từ worker. Chỉ retry lỗi tạm
thời hoặc lỗi tham số có cách khắc phục; tối đa ba attempt cho một operation.
Thiếu thông tin thì hỏi clarification, authorization failure thì không retry,
safety/rights failure thì handoff hoặc fail closed. Reflection không cho phép
model tự nới scope, đổi fact hoặc gọi tool ngoài registry.

Khi deploy graph mới, checkpoint pin `graph_version`. Nếu schema không tương
thích, migration giữ Global Entities đã validate, reset Active Task State và ghi
audit event; không cố deserialize mù quáng.

## Concurrency, interrupt và handoff

- Mỗi conversation có monotonic sequence và OCC version. API đưa message đồng
  thời vào session inbox, chỉ một turn được commit tại một thời điểm.
- Client interrupt phát cancellation xuyên NestJS → FastAPI → provider. Kết quả
  muộn bị fencing token loại bỏ và không được ghi đè state mới.
- Mất WebSocket không hủy handoff. Session/handoff event được lưu bền vững;
  client reconnect fetch history và trạng thái chờ.
- Notification ngoài web chỉ gửi khi có consent/channel policy. Telemetry lỗi
  chạy bất đồng bộ và không được làm chết main flow.

## RAG revision consistency

Drupal publish/update gửi signed, replay-safe webhook. Knowledge pipeline tạo
revision candidate, scan, chunk, embed và đánh giá trước khi atomic activate.
Revision cũ chỉ tombstone sau khi revision mới sẵn sàng.

Critical domain dùng `KnowledgeRevisionState`:

```text
active -> syncing(candidate) -> ready -> atomically active
                           \-> rejected
```

Trong cửa sổ `syncing`, query chạm đúng domain phải suspend ngắn có timeout hoặc
trả “dữ liệu đang cập nhật”; không trộn chunk của hai revision. Non-critical
domain có thể dùng last-known-good theo freshness policy. Webhook đến activation
có SLO riêng; không dùng cron là cơ chế freshness chính.

## Vision và multimodal

Upload chỉ mở khi `authenticated_customer && has_vehicle == true`. UI ẩn control
nhưng NestJS vẫn chặn cứng endpoint bằng RBAC/object authorization. File đi qua
size/type/checksum, malware, decompression-bomb, metadata và retention controls.

Vision/SLM tạo `Observation`, không tạo instruction. OCR text được gắn nguồn ảnh
và phải quay lại semantic/prompt-injection firewall trước khi graph sử dụng.
Ảnh, OCR và derived artifact có deletion lineage để DSAR xóa được toàn bộ.

## Tool và dynamic data

Model chỉ tạo typed proposal theo JSON Schema. NestJS authorize và gọi
System-of-Record adapter. Tool Anomaly Gateway kiểm range, unit, currency,
effective time, revision, cross-field invariant và business conflict trước khi
result trở lại graph. Bất thường trả typed error như `STALE_DATA` hoặc
`BUSINESS_CONFLICT`, không đưa raw value vào câu trả lời.

Session-scoped micro-cache được phép cho read-only dynamic tool theo subject,
market, revision và scope, TTL vài phút theo data owner policy. Không semantic
cache global cho giá/customer data. Cache write chỉ nhận output vượt groundedness
gate; admin có topic/revision invalidation và audit.

## Model Mesh và AI FinOps

Router chọn tier theo risk, complexity, latency, capability và budget; provider
không tạo authority. Prompt tách static policy/few-shot ở prefix ổn định và
dynamic evidence/user state ở cuối để dùng provider prompt caching khi điều khoản
cho phép. Không gửi PII chỉ để tăng cache hit.

Local tier phục vụ bằng vLLM baseline hoặc profile TensorRT-LLM đã benchmark,
không dùng development Python server cho production. Capacity test bao gồm
PagedAttention/KV-cache isolation, continuous batching, fairness, OOM recovery
và multi-tenant data isolation.

Session/user/tenant có token và cost budget. Khi gần hết budget, router hạ tier
chỉ nếu vẫn đạt safety/quality gate; nếu không thì refuse/handoff. Provider
timeout/5xx dùng circuit breaker và fallback cùng capability/risk tier. Nếu mọi
provider thất bại, Static Handoff được kích hoạt.

## UX latency contract

API stream event đã định nghĩa:

- `turn.accepted`
- `task.searching_knowledge`
- `task.checking_tool`
- `task.waiting_for_update`
- `handoff.queued`
- `answer.delta`
- `turn.completed`
- `turn.failed`

Preamble/buy-time buffer phải đúng sự thật và không cam kết kết quả. Hệ thống
không stream hidden chain-of-thought, raw tool payload hoặc policy reasoning.

## Data Flywheel và release

Customer chat không vào training pool theo mặc định. Conversation có lawful
basis/consent phù hợp được redact, purpose-bind và đánh giá tự động; LLM-as-a-Judge
chỉ tạo score/candidate. Human stratified review duyệt 100% high-risk case và mẫu
đại diện trước Dataset Release. Evaluation held-out được tách trước mọi training
candidate.

Prompt, policy, graph schema, retriever, dataset và tool registry là
PromptOps-as-Code. Thay đổi chạy deterministic tests, golden suite tối thiểu 500
case, adversarial tests và independent evidence. Threshold 98% chỉ áp dụng khi
metric/risk profile định nghĩa phù hợp; hard gate như ACL/PII leakage luôn zero.

Release mới chạy offline → shadow 1–5% với privacy/cost cap → canary → promote.
Shadow response không tới khách và không được dùng làm training mặc định.
Rollback/kill switch được kiểm thử.

## Operational containment

- DSAR orchestration xóa/tombstone conversation, checkpoint, cache, telemetry,
  object và derived dataset theo deletion lineage; legal hold phải có authority.
- Observability dùng async buffer/outbox; outage không chặn chat.
- Automated red-team dùng approved attacker profile trong môi trường cô lập,
  rate/cost cap và không tự phát tán harmful content.
- Chaos test chạy staging/internal cohort trước; production experiment cần
  Release/Security approval và blast-radius control.
- Audit turn pin request/response hash, tool evidence, revision và actor trong
  append-only/WORM-capable store. Hash chứng minh integrity, không tự chứng minh
  nội dung đúng; retention/access vẫn tuân thủ privacy/legal.

## Failure matrix tối thiểu

| Failure | Safe outcome |
| --- | --- |
| Thiếu/không fresh evidence | Refuse, waiting state hoặc handoff |
| Tool anomaly | Không hiển thị value; alert và typed failure |
| Message race | Inbox ordering + OCC conflict retry hữu hạn |
| Client disconnect | Cancel generation nếu phù hợp; giữ durable handoff |
| Provider/model outage | Same-tier fallback hoặc Static Handoff |
| pgvector unavailable | Không trả factual RAG answer; handoff |
| Telemetry unavailable | Main flow tiếp tục, buffer có giới hạn |
| Dataset/license chưa duyệt | Chặn trước download/ingestion |
| State version mismatch | Giữ validated global state, reset active task |
| OCR prompt injection | Quarantine observation, refuse/handoff |
