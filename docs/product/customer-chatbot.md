---
id: customer-chatbot-product
title: Customer Chatbot V6
status: active
owner_role: product-owner
scope: cross-system
when_to_read:
  - customer-chatbot
  - customer-conversation
  - support-handoff
  - product-outcome
tags:
  - product
  - chatbot
  - customer-support
revision: 1
review_date: 2026-08-23
supersedes:
  - staging-mvp
---

# Customer Chatbot V6

## Bài toán sản phẩm

Khách hàng cần một kênh CSKH VinFast đáng tin cậy, hiểu tiếng Việt tự nhiên,
giữ được mạch hội thoại và biết khi nào phải chuyển người thật. Doanh nghiệp cần
giảm tải câu hỏi lặp lại nhưng không được đánh đổi bằng thông tin sai về giá,
chính sách, an toàn, tình trạng xe hoặc quyền của khách hàng.

Chatbot không phải “nhân viên tự trị”. Nó là một bề mặt dịch vụ được kiểm soát:
model diễn giải và lựa chọn hành động; source/tool có thẩm quyền cung cấp fact;
API thực thi authorization; human authority quyết định risk và release.

## Audience và profile

| Profile | Khả năng | Ranh giới |
| --- | --- | --- |
| `public_customer` | Hỏi thông tin public đã duyệt, tìm sản phẩm/chính sách/trạm và yêu cầu hỗ trợ | Không đọc customer data, không upload ảnh, không side effect |
| `authenticated_customer` | Khả năng public cộng dữ liệu của chính subject, garage đã được scope, async handoff và Vision khi `has_vehicle=true` | Không đọc customer khác; tool trong V6 là read-only |

Owner assistant và employee/CRM assistant không thuộc V6. Chúng cần profile,
evaluation và release riêng; không kế thừa quyền chỉ bằng cách đổi prompt.

## Capability trong V6

- Conversation session bền vững, stream trạng thái tác vụ và resume khi mất mạng.
- Hiểu intent, chuyển chủ đề và quay lại thực thể đã xác nhận trong session.
- RAG từ approved public knowledge với citation, revision và freshness.
- Read-only tools cho vehicle profile, location và customer-scoped information.
- Clarification, bounded self-correction, refusal và handoff tới CSKH.
- Upload ảnh chỉ cho khách đã đăng nhập và có xe; OCR text phải qua injection
  firewall như user input không tin cậy.
- Quota/token budget cấp session, model fallback và failure state rõ ràng.
- Proactive prompt chỉ khi có consent, policy và frequency cap; không suy diễn
  nhạy cảm hoặc thao túng khách hàng.

## Ngoài phạm vi

- Không đặt lịch, đặt cọc, thanh toán hoặc sửa hồ sơ bằng AI.
- Không chẩn đoán an toàn xe thay kỹ thuật viên; safety-critical case phải handoff.
- Không dùng customer chat làm training data mặc định.
- Không tự crawl/index nội dung VinFast hoặc download dataset chưa có rights.
- Không fine-tune factual knowledge, giá, promotion, policy hoặc authorization.
- Không hiển thị private chain-of-thought. UI chỉ hiển thị status event đã định
  nghĩa như `Đang kiểm tra nguồn` hoặc `Đang kết nối nhân viên`.

## Nguyên tắc câu trả lời

1. Factual claim phải có citation tới source revision active hoặc kết quả tool
   còn freshness; nếu không có thì refuse/handoff.
2. Giá, promotion, bảo hành, safety và legal không được suy đoán từ model memory.
3. Khi source đang đồng bộ ở critical domain, không dùng revision cũ hoặc mới
   một phần; trả trạng thái đang cập nhật.
4. Câu trả lời phải rõ ràng về giới hạn, không giả vờ là người thật và không tạo
   bằng chứng về hành động chưa xảy ra.
5. Handoff lưu được trạng thái dù client offline và cho phép khách quay lại.

## Product acceptance

- 100% factual test case có citation hợp lệ hoặc refusal/handoff đúng policy.
- Zero cross-subject, cross-profile hoặc PII leakage trong security suite.
- 100% case giá, safety, legal, privacy và tool authorization được human review.
- Session resume, concurrent message ordering, cancellation và provider outage
  có deterministic test.
- Prompt/policy/graph/dataset release pin revision, có rollback và kill switch.
- P95 latency, cost/turn, handoff completion, containment/refusal, citation
  correctness và customer satisfaction có SLO được Product/Release Owner duyệt.

Không dùng một chỉ số “accuracy” duy nhất để tuyên bố chatbot không bao giờ sai.
Release decision dựa trên hard safety gates, quality thresholds và evidence theo
từng profile/risk domain.

## KPI cần theo dõi

- Grounded resolution rate và assisted handoff completion.
- Citation correctness, stale-source block và unsupported-claim rate.
- CSAT sau bot/handoff, repeat contact và abandonment.
- P50/P95 latency, token/tool/provider cost trên resolved conversation.
- Safety refusal correctness, false refusal và incident severity.

KPI không được tối ưu bằng cách ép bot trả lời khi thiếu evidence hoặc ngăn khách
tiếp cận nhân viên.
