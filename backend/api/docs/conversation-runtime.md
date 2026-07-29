---
id: api-conversation-runtime
title: Conversation runtime của API Platform
status: active
owner_role: engineering-lead
scope: api
when_to_read:
  - customer-conversation
  - support-handoff
  - session-concurrency
tags:
  - conversation
  - handoff
  - concurrency
  - privacy
revision: 5
review_date: 2026-08-23
supersedes: []
---

# Conversation runtime của API Platform

## Ownership

Context `engagement` sở hữu public conversation contract, object authorization,
session inbox, durable event, quota, notification và support handoff. Nó không
sở hữu LangGraph, retrieval, prompt, model selection hoặc AI evaluation.

`public_customer` dùng unguessable capability được hash trong storage.
`authenticated_customer` luôn kiểm đồng thời issuer, subject, audience và
conversation ownership. Biết `session_id` không tạo quyền đọc hoặc gửi message.

## Message inbox và OCC

Mỗi inbound message có:

- client message ID dùng cho idempotency;
- monotonic `received_sequence`;
- expected conversation version;
- correlation/cancellation ID;
- subject/profile và request budget đã xác minh.

Chỉ một turn được commit trên một conversation version. Message đến khi turn
đang chạy được xếp vào inbox; consumer claim message bằng lease có fencing token.
OCC conflict retry tối đa theo policy và không phát lại provider/tool side effect.
Kết quả từ lease cũ bị loại dù provider trả về thành công.

Runtime worker poll PostgreSQL inbox bằng batch hữu hạn. Mỗi process chỉ chạy tối
đa ba session song song và không chạy đồng thời hai turn của cùng một session;
OCC, lease và fencing trong PostgreSQL mới là authority xuyên process. Khi
internal AI bị tắt, worker không claim turn và public contract chưa được mở.

## Durable conversation context

API PostgreSQL sở hữu projection `ConversationContextEntity`; LangGraph
checkpoint không phải conversation-memory authority. Chỉ reference đã được
business authority xác nhận mới được lưu và truyền qua signed internal request:

```text
kind, opaqueReference, authority, sourceRevision,
confirmedAt, expiresAt, validationState, provenanceDigest
```

Baseline chỉ cho `vehicle_model`, `vehicle_variant`, `market`, `language` với
classification `non_sensitive`. Raw VIN, contact data, exact location và model
observation chưa xác nhận bị từ chối. Mỗi session có tối đa một current value
cho mỗi kind; update context và outbox evidence commit cùng transaction.

Execution context chỉ đọc entity còn `validated`, chưa hết hạn và thuộc đúng
session/access scope. FastAPI nhận opaque reference cùng authority digest; AI
được dùng để resolve follow-up nhưng không được tự promote candidate. Ghi mới
được fence bằng conversation version và `confirmedAt`, nên kết quả cũ không thể
ghi đè entity mới hơn.

Hiện đây là **Candidate foundation**: chưa có production business-tool writer
và chưa có authority adapter để thu hồi/revalidate `sourceRevision`. Cho tới khi
hai phần đó được triển khai, public Chat API vẫn disabled và không được tuyên bố
multi-turn factual capability.

## Durable task context

API PostgreSQL đồng thời sở hữu một `ConversationTaskContext` cho task đang
active hoặc chờ clarification. Context pin task/version, pending slot, opaque
collected slot, source turn, expiry, authorization digest và toàn bộ Assistant
Release binding. Không lưu raw prompt, chain-of-thought, VIN, email, số điện
thoại hoặc model confidence như authority.

Internal AI request và JWT assertion cùng pin `authorizationContextDigest`.
FastAPI chỉ trả typed `ConversationTaskDelta`; repository API kiểm source turn,
release, subject/capability, OCC và fencing trước khi commit delta trong cùng
transaction với completion event và outbox. Task đã đóng, hết hạn hoặc mất
authority không được resume; topic mới phải dùng task ID mới và version khởi
tạo bằng 1. FastAPI đề xuất task mới khi clarification cho thấy một intent khác;
repository chỉ cho phép thay task active khi cả task ID và intent đều đổi, rồi
ghi `replacedTaskId` và `replacementReason=topic_switch` vào outbox. Với answer,
refusal, handoff hoặc tool-refusal terminal, NestJS tự tạo close delta từ task
đang được pin thay vì giao model quyền quyết định vòng đời. Việc đóng/thay task,
completion event và outbox vẫn là một transaction.

Đây vẫn là **Candidate foundation** cho tới khi semantic router, slot authority
adapter và factual multi-turn staging test đạt. Public Chat API tiếp tục
disabled.

## Cancellation

Explicit client cancel, timeout, budget hoặc system shutdown phát cancellation
token qua internal AI client. SSE disconnect không mặc nhiên hủy turn vì client
có thể reconnect. Abort là best-effort: nếu provider không dừng kịp, output muộn
vẫn bị fencing. Disconnect không được tự đóng session hoặc hủy support handoff
đã tạo. Event `turn.cancelled` phân biệt user interrupt, timeout, budget và
system shutdown.

Cancellation của turn đã claim được commit atomically với một outbox event.
Dispatcher claim outbox bằng lease, retry hữu hạn và chuyển terminal failure sang
trạng thái cần vận hành xử lý. Payload chỉ chứa identifier, version, fencing token
và reason; access scope được dựng lại từ dữ liệu session thay vì chép raw identity
vào event. Cancellation dùng lane polling riêng, tối đa ba delivery song song và
vẫn chạy khi cả ba slot turn execution đang bận. Lease luôn dài hơn request
timeout để instance khác không reclaim khi delivery đầu còn in-flight.

## Async handoff và contact center

Handoff là durable aggregate, không phải WebSocket state. Nó lưu:

- conversation/customer scope đã minimize;
- reason code, urgency và safety flag;
- queue/owner reference, status và timestamps;
- last customer-visible event;
- consented notification channels;
- graph/checkpoint revision dùng để correlate execution, không chứa hidden
  reasoning hoặc thay thế transcript.

AI trả `HandoffRecommendation`; recommendation không tạo case và không được ghi
như một tool đã thực thi. Application service của API kiểm object scope, policy,
consent, reason, queue availability và idempotency trước khi tạo handoff.

Lifecycle tối thiểu là:

```text
requested -> queued -> assigned -> connected -> resolved
                    \-> expired | cancelled
connected -> transferred
```

Contact-center adapter nhận outbox event và reconciliation job đối chiếu case
chưa xác nhận. Provider timeout không rollback message/turn đã commit. Callback
từ provider phải xác minh signature, replay key, expected version và transition
hợp lệ; event đến sai thứ tự được giữ để reconciliation hoặc đưa vào operator
queue, không tự sửa aggregate.

Reconnect đọc event history và current handoff state. Agent response khi khách
offline được lưu rồi thông báo qua channel đã consent. Không gửi PII trong push
payload. Timeout/queue outage có escalation rule và audit; AI không tự tiếp quản
lại case đã handoff nếu chưa có explicit transition.

## Token, cost và abuse budget

API áp budget theo request, session, subject/IP và tenant. Input size, attachment,
message rate, concurrent turn và rolling token/cost đều có ceiling. Hạ model tier
chỉ khi AI policy xác nhận đáp ứng safety/quality; hết budget mà không có safe
tier thì refuse hoặc handoff. Mở session mới không mặc nhiên xóa subject-level
abuse/cost window.

## Event và SSE contract

Durable public event chứa:

```text
eventId, schemaVersion, sessionId, turnId, sequence,
type, occurredAt, correlationId, data
```

Event không chứa chain-of-thought, prompt, policy reasoning hoặc raw
tool/provider payload. SSE là projection, không phải source of truth:

- client gửi `Last-Event-ID`; API replay từ durable retention window;
- mobile reconnect trước hết đọc Redis replay buffer tối đa 50 durable event
  gần nhất, TTL 5 phút; cache miss/lỗi Redis quay về PostgreSQL;
- duplicate cursor không nhân đôi semantic event;
- heartbeat chỉ giữ transport sống và không được lưu như conversation message;
- mỗi session có tối đa ba SSE connection trên toàn cluster; admission lease
  nằm trong Redis và connection tự đóng sau 5 phút để client reconnect có kiểm soát;
- buffer theo connection có hard limit; slow consumer nhận typed reconnect
  instruction rồi connection được đóng;
- event quá retention trả typed resync requirement để client fetch message và
  handoff snapshot;
- final answer được persist atomically với outbox trước `answer.completed`.

Public event type tối thiểu gồm `turn.accepted`, `retrieval.started`,
`tool.started`, `answer.delta`, `answer.completed`, `handoff.pending`,
`handoff.connected` và `turn.failed`. Schema version được validate độc lập với
application release để client không phải đoán trạng thái.

Hai control event của transport không được persist vào conversation history:

- `stream.reconnect_required` với `reason=slow_consumer`, `lastEventId` và
  `retryAfterMs`; server đóng stream khi socket buffer vượt 64 KiB;
- `stream.resync_required` với reason `cursor_expired`,
  `cursor_out_of_range` hoặc `retention_expired`, cửa sổ cursor còn khả dụng và recovery action
  `fetch_session_messages_and_handoff_snapshot`.

Cursor nằm đúng trước event cũ nhất còn lưu vẫn hợp lệ. Cursor cũ hơn cửa sổ,
cursor nằm trước một khoảng đã purge hoặc cursor đi trước durable log đều không
được âm thầm coi là “không có event”. Redis chỉ trả replay khi chứng minh cursor
nằm trong buffer 50 event/5 phút; mọi cache miss quay về PostgreSQL để đưa ra
quyết định retention/resync.

## Retry và dead-letter handling

Inbox, AI dispatch, notification và contact-center delivery có retry hữu hạn
theo typed failure. Validation, authorization, stale fencing và permanent policy
failure không retry. Khi vượt attempt limit, record chuyển DLQ với opaque payload
reference, reason, source revision, attempt history và retention. Replay cần
operator capability, expected version và audit; không replay turn đã supersede
hoặc cancelled.

Turn dispatcher hiện lưu `dispatchAttempts`, `dispatchAvailableAt` và failure
code ngay trên durable turn. Lỗi transport transient được exponential backoff
tối đa ba lần; lỗi stale/cancelled bị fencing bỏ qua; policy denial kết thúc bằng
safe refusal. Lỗi hạ tầng không phân loại hoặc transient đã cạn budget tạo audit
`conversation.turn.dispatch.dead-lettered` trước khi commit safe refusal. Chưa
có operator replay API cho dead letter, vì vậy public Chat API vẫn giữ release
gate.

## Data retention và DSAR

Conversation, handoff, attachment reference, notification và token ledger có
classification, retention và deletion lineage. DSAR job:

1. resolve opaque subject qua approved identity mapping;
2. khóa/tombstone dữ liệu đang phục vụ;
3. xóa hoặc legally hold đúng record trong API, AI, cache, object storage và
   telemetry qua idempotent adapters;
4. ghi bằng chứng completion không chứa nội dung đã xóa;
5. retry hữu hạn và đưa unresolved target vào operator queue.

Hash/audit reference không được dùng để lách right-to-erasure. Legal hold cần
authority, purpose và expiry riêng.

## Kiểm thử bắt buộc

- Duplicate message, out-of-order message, OCC conflict và stale fencing token.
- VF 8 → chính sách vay → “chiếc xe lúc nãy”; context hết hạn/cross-session bị chặn.
- Client disconnect/cancel cùng provider response muộn.
- Public capability replay và cross-customer conversation denial.
- Offline handoff, reconnect, notification consent và queue outage.
- SSE Redis replay 5 phút/50 event, cluster quota, maximum lifetime, heartbeat,
  retention expiry, slow consumer và final-answer commit.
- Contact-center callback replay/out-of-order, reconciliation và DLQ replay.
- Session/subject quota, oversized input và budget exhaustion.
- DSAR partial failure, retry, legal hold và derived-data deletion.
