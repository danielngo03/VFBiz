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
revision: 3
review_date: 2026-08-23
supersedes:
  - staging-mvp-boundaries
  - backend-platform-rebuild
---

# Kiến trúc Customer Chatbot V6

Revision 3 ghi nhận các quyết định V7 trên document ID/path ổn định này; V7 không
tạo một nguồn kiến trúc cạnh tranh với V6.

## Bảy lớp và trust boundary

```text
1. Drupal / Customer Portal / client
2. NestJS Edge, identity, quota, inbox và semantic gateway
3. Conversation state, handoff và durable event
4. FastAPI LangGraph Supervisor và policy
5. RAG, read-only tool proposal và anomaly gateway
6. Model Mesh, local/cloud inference, cache và provider fallback
7. Evaluation, PromptOps, audit, telemetry, Dataset Factory và release
```

Client chỉ gọi NestJS. FastAPI là private service và chỉ nhận signed assertion
pin issuer, audience, action, request hash, profile, capability/subject
reference, request budget, revisions, conversation version và fencing token.
Assertion dùng asymmetric allowlist, TTL không quá 60 giây và JTI được consume
atomically một lần; replay store hoặc JWKS verification lỗi thì fail closed.
FastAPI không đọc API PostgreSQL; NestJS không đọc AI PostgreSQL/pgvector.
Tool side effect bị cấm trong text baseline. Handoff không nằm trong tool
registry: FastAPI chỉ tạo `HandoffRecommendation`; NestJS là authority duy nhất
được tạo, đổi trạng thái hoặc đóng support handoff.

## Luồng dữ liệu chính

```text
message
  -> API validate identity/object scope/size/quota/sequence
  -> low-cost policy and semantic classification
  -> session inbox + OCC
  -> signed request to AI
  -> LangGraph Supervisor
  -> retrieval / read-only tool proposal / clarification / refusal /
     HandoffRecommendation
  -> citation and output policy
  -> API policy + optional durable support handoff
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

API PostgreSQL là authority cho conversation, message, turn, public event,
handoff và final answer. LangGraph checkpoint chỉ là execution state có thể
rebuild hoặc migrate; nó không thay thế transcript. Một answer chỉ được commit
khi conversation version và fencing token còn hiện hành. Checkpoint không được
chứa raw bearer token, hidden reasoning hoặc bản sao customer profile vượt quá
scope của turn.

## Concurrency, interrupt và handoff

- Mỗi conversation có monotonic sequence và OCC version. API đưa message đồng
  thời vào session inbox, chỉ một turn được commit tại một thời điểm.
- Client interrupt phát cancellation xuyên NestJS → FastAPI → provider. Kết quả
  muộn bị fencing token loại bỏ và không được ghi đè state mới.
- Mất SSE/kết nối client không hủy handoff. Session/handoff event được lưu bền
  vững; client reconnect fetch history và trạng thái chờ.
- Notification ngoài web chỉ gửi khi có consent/channel policy. Telemetry lỗi
  chạy bất đồng bộ và không được làm chết main flow.

## Contact-center lifecycle

Handoff lifecycle tối thiểu:

```text
recommended -> requested -> queued -> assigned -> connected
                                    \-> expired | cancelled
connected -> resolved | transferred
```

`recommended` chỉ là AI outcome, chưa tạo case. NestJS kiểm customer scope,
reason, queue policy, consent và idempotency trước `requested`. Contact-center
adapter nhận event qua outbox, có reconciliation khi delivery thất bại và không
được làm transaction chat phụ thuộc vào provider. Agent acceptance, response,
transfer và closure đều trở thành durable event. Khi khách offline, response
được persist trước notification; reconnect không tạo handoff hoặc transcript
trùng.

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

## Vision và multimodal sau baseline

Vision không thuộc text baseline. Khi capability này được mở bằng work item và
release evidence riêng, upload chỉ hợp lệ khi `authenticated_customer` có
verified vehicle association. UI ẩn control nhưng NestJS vẫn chặn cứng endpoint
bằng RBAC/object authorization. File đi qua size/type/checksum, malware,
decompression-bomb, metadata và retention controls.

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

## Public event và SSE contract

Contract machine-readable:

- candidate public Conversation transport:
  `contracts/openapi/customer-conversation-candidate-v1.yaml`;
- released customer resources: `contracts/openapi/public-v1.yaml` (không chứa
  candidate operation);
- private API–AI: `contracts/openapi/internal-v1.yaml`;
- event envelope, turn vocabulary và signed assertion claims:
  `contracts/ai/conversation-*.schema.json` cùng
  `contracts/ai/ai-execution-assertion.schema.json`.

`POST .../messages` chỉ trả `202 Accepted`, turn ID, sequence, version và cursor;
không hứa synchronous answer. History và session snapshot là recovery authority.
SSE phát durable projection sau commit và có thể xen connection-local progress
frame. Các public operation đang ở trạng thái contract candidate; runtime chỉ
được công bố active sau work item implementation/cutover có parity evidence.

Durable event envelope gồm:

```text
eventId, schemaVersion, sessionId, turnId, sequence,
type, occurredAt, correlationId, data
```

`eventId` và `sequence` tăng đơn điệu trong conversation đối với durable event.
Transient frame không có hai field này và không được persist. SSE nhận
`Last-Event-ID`, replay event còn retention và không nhân đôi event đã xác nhận.
Heartbeat là transport event không lưu transcript. Server giới hạn buffer theo
connection; slow consumer bị đóng với typed reconnect instruction thay vì làm
tràn memory. Final answer luôn được persist trước `turn.completed`.

Mobile reconnect có thêm Redis replay buffer tối đa 50 durable event gần nhất
trong 5 phút. Buffer chỉ tăng tốc; PostgreSQL vẫn là replay authority khi cache
miss hoặc Redis unavailable. Admission lease giới hạn ba SSE connection cho mỗi
session trên toàn cluster và mỗi connection sống tối đa 5 phút trước controlled
reconnect.

`Last-Event-ID` là cursor của durable event cuối client đã xử lý. Duplicate
cursor không tạo semantic event mới; cursor hết retention trả HTTP
`409 STREAM_CURSOR_EXPIRED` trước khi mở stream để client fetch
snapshot/history. Heartbeat dùng SSE comment 15 giây, không chiếm event
sequence. Mỗi connection có bounded buffer; backpressure hoặc server drain dùng
transient `stream.reconnect_required`, sau đó server đóng connection.

Durable event type v1:

- `message.accepted`
- `turn.processing`
- `turn.completed`
- `handoff.requested`
- `turn.cancelled`

Transient SSE frame v1:

- `retrieval.started`
- `tool.started`
- `stream.reconnect_required`

Projection từ dữ liệu runtime cũ phải explicit: assistant message `answered` có
citation thành `answered`; message không có citation thành `conversational`;
`refused` giữ nguyên. Factual outcome `answered` bắt buộc có ít nhất một
citation; `conversational` và `refused` không mang citation. Không dùng migration
ngầm dựa trên suy đoán nội dung.

Preamble/buy-time buffer phải đúng sự thật và không cam kết kết quả. Hệ thống
baseline chỉ stream typed progress/preamble; không stream model answer delta
trước khi toàn bộ output vượt citation, grounding và safety gate. Hệ thống không
stream hidden chain-of-thought, raw tool payload hoặc policy reasoning.

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
- Inbox/AI/knowledge/contact-center delivery có retry hữu hạn. Event vượt retry
  đi vào DLQ có reason, payload reference đã minimize, replay authority và
  operator audit; DLQ không được trở thành kho lưu PII vô thời hạn.
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
