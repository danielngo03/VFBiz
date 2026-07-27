---
id: VFBIZ-0099
title: Model Mesh provider adapters and PromptOps
status: done
mode: controlled
priority: P0
owner_team: ai-model-platform
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/modules/inference
  - backend/ai/app/infrastructure/model_providers
  - backend/ai/app/platform/config
  - backend/ai/.env.example
  - backend/ai/tests/unit/inference
  - backend/ai/tests/unit/platform
  - backend/ai/tests/integration/inference
  - backend/ai/docs/inference-serving.md
  - backend/ai/docs/evaluation-and-release.md
  - guides/customer-ai
depends_on:
  - VFBIZ-0021
controlled_signals:
  - model-routing
  - provider-fallback
  - ai-finops
  - ai-release
  - pii
exclusive_resources:
  - ai-model-provider-policy
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 5
review_date: "2026-07-25"
updated_at: "2026-07-25T14:47:43.231Z"
---

# Outcome

FastAPI có Model Mesh provider-neutral với ít nhất một inference adapter thật,
Prompt-as-Code versioned và safe disabled mode, để Conversation Graph có thể
generate câu trả lời trong budget mà không đưa provider/model vào domain.

## Constraints

- Provider và model không có product, authorization hoặc release authority.
- Không commit API key, credential, raw prompt, customer PII hoặc provider
  response chứa reasoning vào Git/log/telemetry.
- Fallback chỉ được chuyển sang provider cùng policy/risk tier; không âm thầm hạ
  safety profile để cứu availability.
- Không hardcode model name trong graph/domain; runtime chỉ dùng approved release
  manifest và typed environment config.
- Mọi provider call phải nhận deadline, cancellation, token/cost budget và
  correlation metadata.

## Done when

- Có provider registry, capability/policy tier, circuit breaker và deterministic
  routing theo immutable candidate policy descriptor; runtime activation vẫn
  fail closed cho tới khi VFBIZ-0104 resolve một approved release manifest.
- Có một production-capable cloud adapter cùng fake-server integration tests;
  adapter khác nằm sau cùng port và có typed unsupported outcome, không giả vờ
  đã được hỗ trợ.
- Prompt/system policy/tool schema được pin revision, static prefix tách khỏi
  dynamic customer context và có content hash trong execution evidence.
- Provider timeout, 429, 5xx, malformed output, cancellation, budget exhaustion
  và all-provider outage trả typed outcome; không rò raw error cho customer.
- Usage/cost telemetry được chuẩn hóa và không làm chết main flow.
- Hướng dẫn cấu hình local/staging mô tả exact environment variables, secret
  storage, key rotation, smoke test và rollback mà không yêu cầu Cloud Console
  cho thao tác nội dung nghiệp vụ.

## Checkpoint

- Exact next action: đọc official provider API guidance, khóa inference contract
  và triển khai adapter bằng fake HTTP server trước khi yêu cầu credential thật.

## Evidence

- [x] `npm run verify:ai` — Ruff, Pyright, 191 unit/contract tests và Alembic
  static migration validation passed on 2026-07-25.
- [x] `npm run governance:check` — full deterministic governance gate passed on
  2026-07-25.

## Residual release gate

- Independent review xác nhận candidate Model Mesh đã đóng prompt isolation,
  aggregate attempt budget, provider organization binding, split
  generation/embedding configuration và half-open cancellation cleanup.
- VFBIZ-0104 vẫn là authority bắt buộc cho manifest lookup, approval,
  effective-window, revocation và rollback. VFBIZ-0099 hoàn tất candidate
  implementation nhưng không cấp quyền bật staging dispatch.

### review — 2026-07-25T14:47:43.099Z

Independent review closed Model Mesh implementation blockers; durable activation remains delegated to VFBIZ-0104.

### done — 2026-07-25T14:47:43.231Z

Candidate provider runtime is verified and remains fail-closed until an approved assistant release manifest is resolved.
