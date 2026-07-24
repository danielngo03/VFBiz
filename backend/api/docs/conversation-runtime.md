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
revision: 1
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

## Cancellation

Client interrupt hoặc disconnect phát cancellation token qua internal AI client.
Abort là best-effort: nếu provider không dừng kịp, output muộn vẫn bị fencing.
Disconnect không được tự đóng session hoặc hủy support handoff đã tạo. Event
`turn.cancelled` phân biệt user interrupt, timeout, budget và system shutdown.

## Async handoff

Handoff là durable aggregate, không phải WebSocket state. Nó lưu:

- conversation/customer scope đã minimize;
- reason code, urgency và safety flag;
- queue/owner reference, status và timestamps;
- last customer-visible event;
- consented notification channels;
- AI checkpoint revision cần cho transcript, không chứa hidden reasoning.

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

## Event và streaming contract

Durable event chứa public status/answer, không chứa chain-of-thought hoặc raw
tool/provider payload. WebSocket/SSE là transport projection của event stream;
reconnect dùng cursor và không nhân đôi event. Event schema pin version để client
không đoán trạng thái.

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
- Client disconnect/cancel cùng provider response muộn.
- Public capability replay và cross-customer conversation denial.
- Offline handoff, reconnect, notification consent và queue outage.
- Session/subject quota, oversized input và budget exhaustion.
- DSAR partial failure, retry, legal hold và derived-data deletion.
