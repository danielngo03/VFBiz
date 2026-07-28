---
id: VFBIZ-0130
title: Durable conversation context and AI propagation
status: active
mode: controlled
priority: P0
owner_team: customer-engagement
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
  - ai
  - root
allowed_paths:
  - backend/api/prisma/models/engagement.prisma
  - backend/api/prisma/migrations
  - backend/api/src/modules/engagement
  - backend/api/test
  - backend/ai/app/api/internal_v1
  - backend/ai/app/modules/assistant
  - backend/ai/tests
  - contracts/openapi/internal-v1.yaml
  - docs/work/items/VFBIZ-0130.md
  - backend/api/docs/conversation-runtime.md
  - backend/ai/docs/conversation-graph.md
  - backend/ai/docs/architecture.md
  - backend/ai/docs/inference-serving.md
depends_on: []
controlled_signals:
  - customer-conversation
  - ai-assistant
  - pii
  - migration
  - schema
exclusive_resources:
  - database-migration
  - ai-internal-conversation-contract
required_checks:
  - npm run verify:api
  - npm run verify:ai
  - npm run contracts:lint
  - npm run governance:check
revision: 5
review_date: "2026-07-27"
updated_at: "2026-07-27T16:13:57.807Z"
---

# Outcome

Conversation Runtime lưu các entity đã được business authority xác nhận trong
PostgreSQL và truyền đúng allowlisted references qua signed internal contract
để LangGraph duy trì ngữ cảnh nhiều lượt mà không biến checkpoint hoặc model
output thành nguồn sự thật.

## Constraints

- API PostgreSQL là authority; AI checkpoint chỉ giữ execution state theo turn.
- Chỉ `vehicle_model`, `vehicle_variant`, `market`, `language` với reference
  không nhạy cảm được truyền sang AI. Raw VIN, PII và model-only observation bị cấm.
- Candidate do model trích xuất không được tự promote thành confirmed entity.
- Migration, event/outbox và internal contract thay đổi nguyên tử trong lane này.
- Public Chat API và business tools tiếp tục bị khóa.

## Done when

- Schema có durable context entity projection với authority, revision,
  confirmation time, expiry, validation state và provenance digest.
- Execution context chỉ trả entity thuộc đúng session/subject, còn hiệu lực và
  validated; transport không còn hard-code mảng rỗng.
- OpenAPI, NestJS và Pydantic contract khớp strict field/limit semantics.
  - FastAPI map confirmed entities vào `GlobalEntities`; Knowledge Worker dùng
  task/entity context để tạo retrieval query có cấu trúc, không bỏ qua silently.
- Public RAG contract không nhận customer subject; deterministic router xử lý
  dấu/không dấu, multi-intent và abuse signal theo fail-closed policy.
- Tests chứng minh propagation foundation, expiry, cross-session isolation,
  raw sensitive reference rejection, OCC/version fencing và stale-write
  rejection. Authority-driven source-revision revalidation và một production
  business-tool writer vẫn chưa được triển khai.

## Checkpoint

- Exact next action: implement the authority-backed context writer and
  source-revision revalidation before enabling a factual multi-turn acceptance
  test or composing the public Chat API.

## Evidence

- [x] `npm run verify:api` — 59 suites/330 unit tests and 10 suites/67 E2E tests passed; lint, typecheck, Prisma validate and build passed on 2026-07-27.
- [x] `npm run verify:ai` — Ruff, Pyright, 380 tests and Alembic SQL generation passed on 2026-07-27; 78 external-database tests are intentionally excluded from this fast gate.
- [x] `npm run verify:ai:integration` — all 108 PostgreSQL/pgvector integration tests passed with `VFBIZ_RUN_DB_INTEGRATION=1` on 2026-07-27; zero skips.
- [x] `npm run contracts:lint` — five OpenAPI documents, six runtime schemas and 24 workforce capabilities passed on 2026-07-27.
- [x] `npm run governance:check` — documentation, reports, work schemas and 72 provider-neutral context scenarios passed on 2026-07-27.
- [ ] Supply-chain gate — `npm audit --omit=dev --audit-level=high` still reports 16 high findings; remediation/exception evidence remains a separate release blocker and is not hidden by this work item.

### active — 2026-07-27T16:13:57.807Z

Implemented the durable context propagation foundation, public-RAG isolation
and router safety metadata. No production writer currently confirms business
entities, so multi-turn customer capability is not yet claimed. Source
revalidation and supply-chain findings remain blockers.
