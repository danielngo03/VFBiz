---
id: ai-conversation-graph
title: LangGraph Conversation State Machine
status: active
owner_role: engineering-lead
scope: ai
when_to_read:
  - customer-conversation
  - ai-assistant
  - session-concurrency
  - ai-vision
tags:
  - langgraph
  - state-machine
  - assistant
revision: 6
review_date: 2026-08-23
supersedes: []
---

# LangGraph Conversation State Machine

## Boundary

Module `assistant` sở hữu graph, typed state, Supervisor, clarification,
reflection taxonomy và checkpoint migration. Nó gọi `knowledge` và `inference`
qua application port; tool contract chỉ materialize khi có released registry và
API executor. Nó không authorize customer,
execute business tool hoặc ghi API database.

## State contract

```text
ConversationGraphState
├── global_entities
├── active_task
├── control
└── evidence
```

- `global_entities`: opaque entity do API business authority xác nhận; mỗi field
  pin authority digest, source revision, timestamp, expiry và sensitivity. Chỉ
  promoted field mới được dùng qua intent khác.
- `active_task`: execution projection của durable task context do NestJS sở
  hữu; chỉ gồm intent, pending slot và bounded retry state. FastAPI không tự
  persist task hoặc biến model extraction thành confirmed slot.
- `control`: graph/policy/prompt/knowledge revision, profile, budget, event
  sequence và cancellation/fencing ID.
- `evidence`: citation/tool result reference đã sanitize; không chứa raw secret,
  customer token hoặc untrusted instruction.

Raw customer message dùng `UntrackedValue`: graph được phép đọc trong lần chạy
hiện tại nhưng checkpointer không được persist nội dung này. `completed` chỉ giữ
typed outcome và evidence reference; final answer thuộc durable conversation
store của NestJS. Graph trả final answer qua một `UntrackedValue` riêng để
FastAPI chuyển tiếp nhưng không ghi nó vào checkpoint.

## Supervisor outcome

| Capability | Trạng thái |
|---|---|
| Deterministic fallback router | Implemented |
| VI/EN normalization, multi-intent và abuse signal | Implemented |
| Release-pinned semantic classifier | Candidate |
| Production routing thresholds | Human-blocked |

Mỗi node trả một discriminated outcome:

- `completed`
- `needs_clarification`
- `retryable_failure`
- `non_retryable_failure`
- `policy_denied`
- `handoff_required`
- `cancelled`

Supervisor có thể re-plan khi lỗi transient. Thiếu slot hoặc multi-intent trả
terminal clarification để turn kế tiếp dùng durable context.
Một operation tối đa ba attempt; global graph budget và deadline luôn ưu tiên.
Authorization, ACL, license, PII, safety và stale critical evidence không được
retry bằng cách đổi model hoặc tham số. Worker output không thể tự tăng scope.
Factual completion thiếu evidence reference bị đổi thành refusal trước khi trả
ra ngoài.

`GraphControlState.authorization_context_hash` bind graph execution với
authorization context đã ký. `graph_version` là immutable AI release revision
và pin prompt/tool policy tương ứng; graph không nhận prompt revision tự khai
báo từ client.

## Context switching

Intent mới thay Active Task State hiện tại; baseline chưa giữ task stack.
Global Entities vẫn tồn tại nếu chưa expired/revoked. Pronoun như “xe lúc nãy”
chỉ resolve từ entity đã confirmed, không từ draft. Task-stack/resume nhiều tác
vụ chỉ được thêm khi có use case và contract rõ, không được tuyên bố ngầm.

Durable entity và task projection đều thuộc API PostgreSQL. Internal request
pin `authorizationContextDigest`, release binding, task version, expiry và chỉ
mang allowlisted opaque slot reference. FastAPI map task hợp lệ vào
`ActiveTaskState`; terminal clarification trả `ConversationTaskDelta` có kiểu.
NestJS mới được kiểm OCC/fencing rồi commit delta cùng public event và outbox.
Public retrieval không nhận customer subject. Customer-private facts phải đi
qua NestJS read-only tool có object authorization, không đi qua public RAG.

## Checkpoint migration

Native LangGraph checkpoint là execution-state authority duy nhất. Một
`CheckpointEnvelope` execution-only giới hạn 32 KiB chỉ là projection dùng để
validate và băm binding; envelope không được persist như một state store song
song. Resume gate chỉ lưu metadata tối thiểu gồm exact native checkpoint ID,
envelope digest, interrupt nonce, trạng thái CAS và fencing token.

`ConversationGraphRuntime` là durable start/resume boundary; bare
`Command(resume=...)` không phải API runtime được hỗ trợ. Runtime tự sinh
`thread_id` từ session, turn và graph version, pin exact checkpoint ID và không
nhận LangGraph config từ caller. Resume gate chuyển atomically từ `waiting`
sang `claimed`; hai request cạnh tranh chỉ một request được chạy worker. Crash
sau claim fail closed và đi qua recovery/handoff, không tự chạy lại operation.
Turn start phải reserve key bằng insert-if-absent trước khi chạy graph; retry
cùng identity không thể overwrite record `waiting`, `claimed` hoặc `terminal`.

Khi có safe version migration trong cùng security boundary:

1. giữ Global Entities còn hợp lệ theo allowlist;
2. xóa Active Task State/evidence tạm;
3. tạo customer-safe resume event;
4. audit reason và old/new revision.

Serializer phải cấu hình explicit strict allowlist, tắt pickle fallback và
không được dùng default permissive deserialization. Raw message, final answer,
prompt, token và PII không nằm trong tracked channel.
`source_revision` trong entity chỉ là SHA-256 lowercase gồm đúng 64 ký tự hex;
không nhận namespace, URI, email, filename hoặc business text.

Resume trực tiếp chỉ hợp lệ khi identity, native checkpoint ID, envelope digest,
interrupt nonce, state schema, graph, policy,
knowledge, assistant profile, authorization hash, conversation version và
fencing token cùng khớp. Session, turn, profile, authorization, conversation hay
fencing mismatch xóa toàn bộ state và entity. Schema/graph/policy/knowledge
revision đổi trong cùng security boundary chỉ giữ entity được authority hiện
tại revalidate; active task và evidence luôn reset.
`CheckpointIdentity.graph_version` và `GraphControlState.graph_version` phải
khớp trước khi đọc checkpoint; mismatch fail closed trước mọi deserialization.

## Cancellation và Vision

Cancellation được kiểm giữa node và truyền xuống provider adapter. Output sau
fencing token hết hiệu lực bị drop. Vision kết quả là `Observation` với source,
confidence và scan state; OCR text phải đạt multimodal injection policy trước
khi vào active task. Observation không bao giờ là system instruction.

## Runtime ports

- `SupervisorPort` trả strict routing metadata gồm intent, confidence, slots,
  multi-intent, OOD và abuse signal. Deterministic router là fallback an toàn;
  semantic classifier chỉ được compose khi có release/evaluation evidence.
- `TaskWorkerPort` chỉ trả discriminated result cùng evidence reference đã
  sanitize; provider, retrieval và business tool vẫn nằm sau port.
- Worker không được tự khai báo câu trả lời là factual/non-factual. Grounding
  policy được code sở hữu theo intent/profile; `EvidenceAuthorityPort` kiểm digest,
  revision, ACL và freshness trước completion.
- Supervisor, execution control, evidence authority, checkpoint I/O và worker
  đều bị giới hạn bởi turn deadline; repository finalize có timeout riêng ngắn.
- Worker bắt buộc echo fencing token. Trong khi worker chạy, graph race deadline
  và invalidation signal để hủy provider task; sau khi trả về graph vẫn kiểm lại
  deadline và `ExecutionControlPort`; missing/stale authority luôn fail closed.
- Cleanup sau cancellation có grace period hữu hạn. Adapter/provider không tuân
  thủ cancellation được tách khỏi request path; callback chỉ thu hồi exception,
  còn late result vẫn bị fencing chặn và không thể commit.
- `retryable_failure` được chạy lại tối đa ba lần. `policy_denied` và
  `non_retryable_failure` kết thúc ngay, không đổi model để né policy.
- Clarification là terminal outcome của turn hiện tại, mang message, opaque slot
  name và signed task delta; baseline không dùng native cross-turn
  `interrupt()`. Tin nhắn kế tiếp tạo turn mới, nhận lại confirmed entity và
  task context đã được NestJS commit. Clarification có intent mới tạo task ID
  mới với `expectedTaskVersion = 0`; clarification `unknown` giữ task hiện tại
  để multi-intent ambiguity không vô tình hủy authority. FastAPI không đóng
  task: NestJS tự tạo close delta cho answer, refusal, handoff hoặc tool-refusal
  terminal và commit atomically với event/outbox.
- Cancellation/deadline được kiểm trước route và worker; result có fencing token
  cũ bị chuyển thành `cancelled`, không được dùng làm final answer.

Khi Assistant Release có semantic-classifier binding hợp lệ, keyword match chỉ
là tín hiệu fallback và confidence của nó bị giới hạn ở `0.6`; semantic
classifier được gọi để xác nhận hoặc sửa intent. Nếu binding thiếu, hết hạn,
classifier lỗi hoặc trả output không hợp lệ, supervisor giữ route deterministic
đã cap và gắn reason code fallback. Vì vậy keyword không thể tự trở thành
authority chỉ nhờ một chuỗi trùng khớp.

## Kiểm thử

- Chuyển VF 8 → finance → quay lại “xe lúc nãy”.
- Missing slot tạo clarification, không retry tool mù quáng.
- Transient tool/provider failure retry hữu hạn; authorization failure không retry.
- Cancellation giữa retrieval/generation và late-result fencing.
- Checkpoint compatible/incompatible migration.
- Cross-session/tampered checkpoint bị từ chối trước worker.
- Concurrent resume chỉ có một CAS winner.
- Permissive serializer và unregistered constructor không được phục hồi.
- OCR instruction không thay graph policy.
