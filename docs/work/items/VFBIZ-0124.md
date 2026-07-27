---
id: VFBIZ-0124
title: Calibrate Vietnamese grounding validator
status: proposed
mode: controlled
priority: P0
owner_team: ai-assurance
accountable_role: release-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/modules/evaluation
  - backend/ai/tests/evaluation
  - backend/ai/tests/security
  - backend/ai/docs/evaluation-and-release.md
depends_on:
  - VFBIZ-0110
  - VFBIZ-0115
controlled_signals:
  - grounding
  - ai-safety
  - ai-release
  - ai-evaluation
exclusive_resources:
  - ai-grounding-validator
  - ai-release-evidence
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 1
review_date: "2026-08-26"
---

# Outcome

Một independent Vietnamese grounding validator phát hành factual answer chỉ khi
claim được evidence của đúng active release hỗ trợ; validator xử lý paraphrase,
numeric/entity/negation/temporal contradiction và giữ false-negative safety
gate được calibration trên held-out VinFast-approved suite.

## Constraints

- Citation membership và lexical equality là deterministic gates nhưng không đủ
  chứng minh entailment.
- Generator self-confidence hoặc cùng generator model không được là authority.
- NLI/judge chỉ là một signal trong ensemble; high-risk price, safety, legal,
  PII và authorization cần deterministic checks cùng human-reviewed cases.
- Validator pin model/rules/threshold/calibration dataset/evaluator revision,
  có budget, timeout, cancellation và fail-closed behavior.
- Evaluation và training split tách biệt; không đưa held-out failures ngược vào
  tuning trước khi tạo suite revision mới.

## Done when

- Claim segmentation bảo toàn số, đơn vị, phủ định, entity, thời gian và phạm vi
  thị trường trong tiếng Việt/Anh.
- Ensemble kết hợp citation membership, numeric/entity/temporal rules,
  contradiction detector và approved NLI signal.
- Calibration báo precision/recall, unsupported-claim false negative, refusal
  accuracy, ECE và per-risk-domain threshold trên held-out suite.
- Poisoned evidence, cross-revision, partial support, conflicting sources và
  judge outage đều không phát hành factual answer.
- Shadow evidence so sánh exact baseline và candidate validator; Release Owner
  chỉ activate bằng signed manifest và có rollback/kill switch.

## Checkpoint

- Exact next action: chạy sau VFBIZ-0110 bake-off và VFBIZ-0115 runtime binding,
  dùng cùng trusted retrieval snapshot contract.

## Evidence

- [ ] `npm run verify:ai` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
