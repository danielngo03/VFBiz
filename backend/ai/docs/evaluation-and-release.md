---
id: ai-evaluation-release
title: AI evaluation và release evidence
status: active
owner_role: engineering-lead
scope: ai
when_to_read:
  - ai-evaluation
  - ai-release
  - fine-tuning
tags:
  - evaluation
  - release
  - ai-safety
revision: 2026-07-25.2
review_date: 2026-08-23
supersedes:
  - ai-security-profiles-release
---

# AI evaluation và release evidence

## Separation of duties

Candidate author xây model/prompt/retriever/tool/dataset revision. AI Assurance
định nghĩa held-out suite và tạo immutable evaluation evidence. Data, Security,
Privacy/Legal owners quyết phần risk thuộc authority của họ; Release Owner mới
được promote, rollback hoặc dừng release. Một run không được tự đổi role để tự
review/approve candidate của chính nó.

## Release unit

`AIReleaseManifest` pin assistant profile, model/provider, prompt, policy,
embedding, retriever, dataset, tool registry và evaluation-suite revision. Mỗi
candidate có author, base release, change reason, expiry/review date, rollback
target và kill switch.

Prompt là code versioned. Runtime request phải ghi nhận `prompt_revision`,
`model_revision` và `policy_profile`; không dùng mutable dashboard prompt như
nguồn chuẩn. Provider adapter không tự promote model hoặc đổi prompt khi API
fallback. Thay một trong ba revision tạo candidate release mới.

Evaluation evidence phải pin:

- candidate/suite/evaluator revision và environment;
- source hashes, seed/sampling policy và run timestamp;
- per-gate result, metric definition/version và baseline comparison;
- redacted failure examples, evidence hash và residual risk;
- repeatability result trên số run được acceptance yêu cầu.

## Hard gate và quality threshold

| Gate | Kiểu | Quy tắc |
| --- | --- | --- |
| Cross-ACL/cross-subject/PII leakage | Hard | Zero failure; không average |
| Citation validity cho factual response | Hard | Citation hợp lệ hoặc refusal/handoff |
| Tool authorization/schema/disabled mode | Hard | Mọi negative case phải bị từ chối |
| Provenance, rollback, kill switch | Hard | Thiếu evidence là `failed-safely` |
| Groundedness/usefulness/refusal quality | Threshold | Versioned target theo profile/use case |
| Latency/cost | Threshold | So với budget/SLO đang được duyệt |

Hard gate không được làm mềm thành tỷ lệ trung bình. Refusal/handoff đúng policy
không bị tính như factual answer thiếu citation.

## Suite isolation và contamination

Public, authenticated-customer và employee profile có suite/release evidence
riêng. Evaluation và red-team records không đi vào retrieval hoặc training
candidate. Trước run cần kiểm overlap/hash/near-duplicate với knowledge/training
sources; contamination hoặc evaluator không độc lập phải được ghi và chặn gate
khi chưa có quyết định của authority phù hợp.

## Release states và failure

```text
candidate -> evaluated -> decision-ready -> approved -> promoted
                      \-> rejected | expired
promoted -> monitored -> rolled-back | retired
```

Evaluation service chỉ tạo evidence và trạng thái `decision-ready`; không
promote/deploy. Provider outage, cost regression hoặc failure khó tái lập không
được retry vô hạn: tối đa hai lần cùng nguyên nhân rồi trả `needs-decision`.
Fine-tuning chỉ mở qua ADR/evidence sau khi prompt/RAG/tooling không đáp ứng một
hành vi ổn định; không dùng để sửa freshness, provenance hoặc authorization.

## PromptOps, shadow và automated evaluation

Thay đổi prompt, policy, graph schema, retriever, dataset, embedding hoặc tool
registry phải tạo candidate release và chạy:

1. deterministic/unit/contract suite;
2. golden suite tối thiểu 500 case theo profile/risk;
3. automated adversarial suite;
4. LLM-as-a-Judge với rubric/evaluator revision đã pin;
5. human stratified review, gồm 100% high-risk case;
6. shadow 1–5% với privacy/cost cap trước canary khi áp dụng.

Provider contract suite còn bắt buộc kiểm:

- `store=false` và retention policy/ZDR/MAM approval evidence được kiểm riêng;
- structured output strict, schema drift và unknown citation bị từ chối;
- exact returned model snapshot, prompt content hash và immutable deployment
  descriptor;
- timeout/cancellation thực sự hủy network work trong khả năng transport;
- response byte/output limits, bulkhead, request/session cost budget và usage
  mapping;
- same-policy fallback, all-provider outage và disabled mode;
- claim-support/entailment gate độc lập; citation membership không đủ để đạt
  groundedness;
- safety identifier đã băm, telemetry không chứa credential/raw prompt/raw
  provider body.

Mục tiêu tổng 98% chỉ có ý nghĩa khi metric và sample được phê duyệt. Hard gate
ACL/PII/tool authorization/citation validity luôn zero failure, không được bù
bằng average. Judge không tự approve/release và output shadow không tới khách.

Fine-tuning kỹ năng/văn phong có thể được xem xét sau khi có Dataset Release,
held-out suite, privacy/rights evidence và rollback. Handoff log không tự động
trở thành training data.
