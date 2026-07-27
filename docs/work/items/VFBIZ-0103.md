---
id: VFBIZ-0103
title: Provider-neutral embedding adapters and cost controls
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
  - backend/ai/app/infrastructure/embedding_providers
  - backend/ai/app/platform/config
  - backend/ai/.env.example
  - backend/ai/tests/unit/inference
  - backend/ai/tests/integration/inference
  - backend/ai/docs/inference-serving.md
  - guides/customer-ai
depends_on:
  - VFBIZ-0099
  - VFBIZ-0107
  - VFBIZ-0108
  - VFBIZ-0111
controlled_signals:
  - ai-retrieval
  - model-routing
  - provider-fallback
  - ai-finops
  - ai-release
exclusive_resources:
  - ai-model-provider-policy
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 7
review_date: "2026-07-26"
updated_at: "2026-07-26T04:48:19.054Z"
---

# Outcome

AI Model Platform cung cấp provider-neutral embedding adapters, typed usage/cost
ledger và candidate deployments cho managed cùng self-hosted serving. Provider
production chỉ được chọn sau Vietnamese/VinFast retrieval bake-off.

## Constraints

- Embedding provider không có release, ACL hoặc source approval authority.
- OpenAI, Vertex hoặc self-hosted đều chỉ là candidate; không chọn provider bằng
  environment variable, public leaderboard hoặc convenience.
- Query text/evidence không được ghi raw vào telemetry/provider metadata.
- Model revision và output dimension phải khớp Knowledge Release; mismatch
  fail-closed, không pad/truncate vector.
- Batch ingestion có byte/item/token ceiling, retry hữu hạn và cancellation.
- Không commit API key hoặc provider response/vector fixture lớn vào Git.

## Done when

- Implement exact typed embedding contract do VFBIZ-0107 phát hành cho query và
  bounded batch ingestion.
- Có ít nhất một managed candidate và một self-hosted-compatible candidate sau
  cùng port; adapter chưa được runtime activate trước release decision.
- Adapter validate exact response count/order/index, finite vector, dimension,
  model revision, usage, deadline/cancellation và typed 401/429/5xx/malformed.
- Mỗi adapter có token/item/byte/cost budget, normalized usage ledger, bulkhead,
  cancellation và circuit health không dùng chung với generation.
- Fake HTTP integration test bao phủ success, order mismatch, dimension mismatch,
  rate limit, timeout, cancellation và no-key fail-closed.
- Guide mô tả ADC/workload identity, secret, residency, data controls, cost,
  smoke và rollback mà không mặc định OpenAI.

## Checkpoint

- Exact next action: VFBIZ-0104 pin generation identity vào durable
  `AIReleaseManifest`; Knowledge owner compose cùng identity cho query/index.
- Không runtime-activate candidate chỉ từ environment. VFBIZ-0103 hoàn tất
  adapter foundation, không tuyên bố provider đã được duyệt staging.

## Evidence

- [x] `npm run verify:ai` — 229 passed; Ruff/Pyright/Alembic đạt
- [x] `npm run governance:check` — docs/reports/guides/authorization/work/agent
  governance và 61 provider-neutral scenarios đạt
- [x] `VFBIZ_RUN_DB_INTEGRATION=1 ... npm run verify:ai:integration` — 36 passed
- [x] focused embedding suite — 23 passed
- [x] `npm run guides:check` — 12 guide documents đạt
- [x] Independent Model/FinOps review — prior cancellation, response ceiling,
  vector-space identity, rendered-input budget và mixed-replica findings đã sửa
- [x] Commits `362da83`, `1d48c6d`, `4b1914c`, `8a55f8e`
