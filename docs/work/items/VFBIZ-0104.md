---
id: VFBIZ-0104
title: Grounding assurance and assistant release manifest
status: done
mode: controlled
priority: P0
owner_team: ai-assurance
accountable_role: release-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/modules/evaluation
  - backend/ai/app/modules/governance
  - backend/ai/tests/evaluation
  - backend/ai/tests/security
  - backend/ai/docs/evaluation-and-release.md
  - backend/ai/docs/safety-and-abuse.md
depends_on:
  - VFBIZ-0025
  - VFBIZ-0099
  - VFBIZ-0103
  - VFBIZ-0108
controlled_signals:
  - ai-release
  - ai-safety
  - ai-retrieval
  - model-routing
exclusive_resources:
  - ai-assistant-release-manifest
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 5
review_date: "2026-08-25"
updated_at: "2026-07-26T05:24:14.390Z"
---

# Outcome

Factual answer chỉ được phát hành khi một independent grounding validator xác
minh claim-support trên exact evidence snapshot và immutable Assistant Release
Manifest pin toàn bộ model/prompt/schema/policy/knowledge/tool revisions.

## Constraints

- Validator không được chỉ kiểm citation membership hoặc tự tin của LLM sinh câu
  trả lời.
- Generator, evaluator và release approver không được là cùng một authority.
- Giá, safety, legal, PII và authorization cases cần human-reviewed evidence;
  không dùng LLM-as-a-Judge làm release authority duy nhất.
- Manifest không chứa API key, prompt/customer raw text hoặc mutable alias.
- Khi validator/model/evaluation unavailable hoặc revision mismatch, kết quả
  phải fail closed thành refusal/handoff, không hạ safety profile.

## Done when

- Có typed claim/answer segmentation và deterministic/NLI validator port với
  exact validator revision, evidence digest, thresholds và bounded input.
- Evaluation suite đo unsupported-claim false negative, refusal accuracy,
  citation entailment và VI/EN behavior trên held-out cases.
- Assistant Release Manifest có content hash và pin model deployment, prompt,
  output schema, graph, policy, validator, knowledge profile, retriever,
  embedding index generation, dataset và tool registry.
- Domain resolver contract kiểm automated gate, human approval, artifact digest,
  effective window, expiry, revocation, assistant profile và environment;
  `.env` hash không phải release authority.
- Persistence, activation history, exact rollback và runtime composition được
  giao cho `VFBIZ-0114`; Model Mesh/embedding/retrieval/final-commit binding được
  giao cho `VFBIZ-0115`.
- Negative tests chứng minh wrong digest/revision, unsupported numeric claim,
  partial citation, stale evidence và unavailable validator đều không phát hành
  factual answer.

## Checkpoint

- Domain contract đã được review độc lập; exact next action là triển khai
  PostgreSQL authority trong `VFBIZ-0114`, sau đó runtime binding trong
  `VFBIZ-0115`.

## Evidence

- [x] `npm run verify:ai` — 247 passed, Ruff/Pyright/Alembic đạt tại `1d5b1c8`
- [x] PostgreSQL integration — 36 passed, không skip tại `1d5b1c8`
- [x] Independent review — hai P0 đã đóng; 16 focused tests, Ruff và Pyright đạt
- [x] `npm run governance:check` — docs/guides/contracts và 61 scenarios đạt
