---
id: security-data-ai
title: Baseline Security, Data và AI
status: active
owner_role: security-owner
scope: root
when_to_read:
  - security
  - privacy
  - data
  - ai
  - controlled
tags:
  - security
  - privacy
  - data
  - ai
revision: 4
review_date: 2026-09-01
supersedes: []
---

# Baseline Security, Data và AI

Đây là baseline active cho staging và implementation. Tài liệu không cấp quyền
production; Security, Privacy và Data Owner phải phê duyệt control thuộc thẩm
quyền cùng residual risk trước production release.

## Security và Data

- Production access và risk exception áp dụng least privilege, separation of
  duties và named human approval.
- Business capability là code-owned contract; quản trị viên chỉ ghép capability
  thành role và assignment trong phạm vi được phép, không tạo permission string
  hoặc wildcard mới.
- Workforce authorization là deny-by-default. Quyền nhạy cảm/đặc quyền cần MFA
  assurance, expiry và maker-checker; không self-elevation, self-approval hoặc
  vô hiệu hóa quản trị viên cuối cùng.
- Browser và UI không phải enforcement authority. Workforce token nằm
  server-side; API xác minh entitlement revision, organizational scope và object
  relationship trên mọi action.
- Secret nằm trong secret manager; PII bị redact khỏi log, prompt, trace,
  fixture và analytics.
- Mọi data source cần owner, purpose, provenance/license, classification, ACL,
  retention, deletion và freshness rule.
- Public, customer-scoped và employee data tách biệt. Production data không
  được sao chép vào Git hoặc model/tool chưa được duyệt.
- CI và repository policy mới là enforcement authority cho test, review, scan
  và protected branch; agent prose chỉ là defense-in-depth.
- Public dataset hoặc VinFast content không được download/crawl/index trước
  Source Register approval. Dataset Card là evidence tham khảo, không thay Legal
  review; generator và reviewer/release authority phải tách biệt.

## AI profile

- `public_customer`: chỉ approved public knowledge.
- `authenticated_customer`: subject-scoped retrieval và least-privilege read tools.
- Owner/employee assistant tương lai phải có profile, ACL, suite và release riêng.

Các profile không dùng chung unscoped index, prompt, cache hoặc tool registry.
Retrieval lọc ACL trước ranking và kiểm tra lại trước response.

## Tiêu chuẩn correctness

- Factual answer phải cite approved source revision/freshness hoặc refuse/handoff.
- Live fact, calculation và action đến từ authorized API tool, không từ model memory.
- Side effect cần caller authorization, schema validation, confirmation,
  idempotency, audit và kill switch.
- Release pin model, prompt, policy, retriever, dataset, embedding và tool.
- Fine-tuning không phải mặc định; chỉ dùng cho stable behavior sau evidence,
  không dùng để sửa stale fact hoặc access control.

Không tài liệu nào được hứa AI “không bao giờ sai”. Hard gate là zero known
ACL/PII leakage trong security suite và mọi factual test đều có citation hợp lệ
hoặc refusal/handoff.
