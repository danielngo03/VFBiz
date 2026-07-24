---
id: ai-safety-abuse
title: AI safety and abuse controls
status: active
owner_role: security-owner
scope: ai
when_to_read:
  - ai-safety
  - prompt-injection
  - data-poisoning
  - ai-tool
  - ai-incident
  - ai-vision
  - multimodal-injection
tags:
  - ai
  - security
  - abuse
revision: 2026-07-23.2
review_date: 2026-08-23
supersedes:
  - ai-security-profiles-release
---

# AI safety and abuse controls

Tài liệu này chỉ sở hữu abuse controls, containment và safety evidence của
AI Platform. Data governance, evaluation acceptance và production release vẫn
thuộc các human authority được định tuyến từ repository root.

## Abuse boundaries

| Abuse path | Control | Safe outcome |
|---|---|---|
| Prompt injection | Treat retrieved/user content as data; pin system policy | refuse or hand off |
| Poisoned or stale source | provenance, revision, freshness, quarantine and tombstone | exclude source revision |
| Cross-profile or cross-subject retrieval | filter ACL before ranking and recheck before response | deny without provider call |
| Tool misuse or replay | typed proposal, least scope, quota and correlation ID | API rejects or disables tool |
| Sensitive-data disclosure | classify, redact and prohibit raw prompt/provider payload logs | redact, refuse and alert |
| Multimodal OCR injection | Vision output là observation; quét injection sau OCR | quarantine observation |
| Semantic cache poisoning | chỉ cache grounded output, pin revision, topic panic invalidation | bypass/invalidate cache |
| State poisoning | entity promotion có source/confidence/schema; checkpoint versioned | reject/reset active task |
| Automated attacker abuse | isolated red-team identity, quota, no production side effect | contain and preserve evidence |

Public, authenticated-customer and employee profiles never share an unscoped
index, prompt, cache key or tool authority. Model output and retrieved content
cannot increase the scope in the signed gateway assertion. Customer chat is not
training data by default.

## Delivery and release separation

- The builder may implement a candidate and run the deterministic suites, but
  cannot independently accept its own evidence.
- An independent evaluator verifies the pinned suite, candidate revision and
  observed results. A gate records pass/fail evidence only.
- Data, Privacy and Security owners decide within their named authority; they do
  not deploy the candidate.
- The Release Owner alone authorizes promotion, rollback or production release.

Missing provenance, profile isolation, reliable evaluation, rollback or kill
switch is a failed-safe exit, not an approval exception.

## Multimodal và red-team

Ảnh chỉ được nhận qua API RBAC/quarantine. OCR text không đi thẳng vào prompt;
nó quay lại injection classifier và policy như untrusted user content. EXIF,
steganography suspicion, document instruction và unsafe automotive observation
được flag/handoff thay vì để model tự chẩn đoán.

Automated red-team chạy trong environment/profile cô lập, dùng synthetic target,
budget/rate cap và kill switch. Attacker model không có production credential,
network tự do hoặc side-effect tool. Generated harmful cases thuộc restricted
red-team dataset; human reviewer chỉ nhận sample/evidence đã minimize.

## Containment and recovery

1. Disable the affected release, profile, provider or tool through the approved
   kill switch; do not broaden another profile as a fallback.
2. Quarantine the implicated source or candidate revision and preserve redacted,
   immutable evidence with correlation IDs.
3. Route data, privacy, security and legal findings only to the affected human
   authorities. Do not let an agent accept residual risk.
4. Let the Release Owner select the approved rollback revision and record the
   decision separately from evaluation evidence.

Use `../../../docs/governance/security-data-ai.md` for the cross-system baseline and
the active Git work item for approved scope. Do not copy temporary release scope
into this durable safety document.
