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
revision: 1
review_date: 2026-08-23
supersedes: []
---

# LangGraph Conversation State Machine

## Boundary

Module `assistant` sở hữu graph, typed state, Supervisor, clarification,
reflection taxonomy, interrupt và checkpoint migration. Nó gọi `knowledge`,
`inference` và `tooling` qua application port. Nó không authorize customer,
execute business tool hoặc ghi API database.

## State contract

```text
ConversationGraphState
├── global_entities
├── active_task
├── control
└── evidence
```

- `global_entities`: entity đã xác nhận; mỗi field pin origin, confidence,
  timestamp và sensitivity. Chỉ promoted field mới được dùng qua intent khác.
- `active_task`: intent, slots, current node, attempt, pending clarification và
  interrupt token. Task mới có thể đọc global entity nhưng không tự promote output.
- `control`: graph/policy/prompt/knowledge revision, profile, budget, event
  sequence và cancellation/fencing ID.
- `evidence`: citation/tool result reference đã sanitize; không chứa raw secret,
  customer token hoặc untrusted instruction.

## Supervisor outcome

Mỗi node trả một discriminated outcome:

- `completed`
- `needs_clarification`
- `retryable_failure`
- `non_retryable_failure`
- `policy_denied`
- `handoff_required`
- `cancelled`

Supervisor có thể re-plan khi lỗi transient hoặc thiếu slot có thể hỏi khách.
Một operation tối đa ba attempt; global graph budget và deadline luôn ưu tiên.
Authorization, ACL, license, PII, safety và stale critical evidence không được
retry bằng cách đổi model hoặc tham số. Worker output không thể tự tăng scope.

## Context switching

Intent mới freeze Active Task State cũ bằng typed checkpoint. Global Entities
vẫn tồn tại nếu chưa expired/revoked. Khi quay lại, graph chỉ resume nếu profile,
policy, graph và evidence revision còn tương thích; nếu không thì revalidate.
Pronoun như “xe lúc nãy” chỉ resolve từ entity đã confirmed, không từ draft.

## Checkpoint migration

Checkpoint pin `graph_version` và state schema version. Migration registry phải
deterministic và test bằng fixture của mọi supported version. Khi không có safe
migration:

1. giữ Global Entities còn hợp lệ theo allowlist;
2. xóa Active Task State/evidence tạm;
3. tạo customer-safe resume event;
4. audit reason và old/new revision.

Không unpickle/deserialize arbitrary class từ checkpoint.

## Interrupt và Vision

Cancellation được kiểm giữa node và truyền xuống provider adapter. Output sau
fencing token hết hiệu lực bị drop. Vision kết quả là `Observation` với source,
confidence và scan state; OCR text phải đạt multimodal injection policy trước
khi vào active task. Observation không bao giờ là system instruction.

## Kiểm thử

- Chuyển VF 8 → finance → quay lại “xe lúc nãy”.
- Missing slot tạo clarification, không retry tool mù quáng.
- Transient tool/provider failure retry hữu hạn; authorization failure không retry.
- Interrupt giữa retrieval/generation và late-result fencing.
- Checkpoint compatible/incompatible migration.
- OCR instruction không thay graph policy.
