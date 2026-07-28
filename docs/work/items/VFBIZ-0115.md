---
id: VFBIZ-0115
title: Bind release-grounding authority to Model Mesh
status: active
mode: controlled
priority: P0
owner_team: ai-model-platform
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/bootstrap
  - backend/ai/app/api/internal_v1
  - backend/ai/app/modules/evaluation/application
  - backend/ai/app/modules/inference/application
  - backend/ai/app/modules/governance/application
  - backend/ai/app/modules/governance/infrastructure
  - backend/ai/app/modules/knowledge/application
  - backend/ai/app/modules/assistant/infrastructure
  - backend/ai/app/infrastructure/model_providers
  - backend/ai/app/infrastructure/embedding_providers
  - backend/ai/app/platform/config
  - backend/ai/tests/unit/evaluation
  - backend/ai/tests/unit/inference
  - backend/ai/tests/unit/assistant
  - backend/ai/tests/unit/bootstrap
  - backend/ai/tests/contract
  - backend/ai/tests/integration/inference
  - backend/ai/tests/integration/platform
depends_on:
  - VFBIZ-0104
  - VFBIZ-0114
  - VFBIZ-0126
controlled_signals:
  - ai-release
  - ai-safety
  - model-routing
  - grounding
exclusive_resources:
  - ai-model-provider-policy
  - ai-assistant-release-manifest
  - ai-embedding-index-generation
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 4
review_date: "2026-08-26"
updated_at: "2026-07-27T08:20:00.000Z"
---

# Outcome

Mọi generation và retrieval query trong Customer Assistant chỉ chạy bằng
provider/model/embedding generation được resolved từ cùng active Assistant
Release; output chỉ được commit khi Grounding Assurance xác minh trusted
retrieval snapshot và exact release identity.

## Constraints

- Generation và embedding là lifecycle, credential, budget, circuit và release
  identity độc lập.
- Generation và embedding có project/service identity, secret reference,
  retention/data-control approval và rotation lifecycle độc lập. Cùng project
  chỉ được dùng khi release evidence phê duyệt rõ, không phải do một config
  object bắt buộc dùng chung.
- Không hot-fallback embedding sang vector space khác. Fallback chỉ dùng index
  đã materialize đầy đủ và được atomic activate.
- Offline document embedding và online query embedding dùng cùng
  `EmbeddingRuntime`, generation identity và templates đã pin.
- Grounding snapshot do Knowledge authority tạo; caller không tự khai evidence,
  time, ACL hoặc active revision.
- Model output không được tự tạo handoff hoặc business mutation.
- Không thêm provider/model mới nếu chưa có contract, benchmark và release
  evidence.

## Done when

- Model Mesh nhận resolved release snapshot thay vì mutable environment hash.
- Knowledge retrieval trả trusted snapshot handle có release, pointer, ACL,
  retriever, knowledge và evidence digests.
- Grounding chặn cross-profile, cross-ACL, cross-revision, stale/tampered
  evidence, unsafe discourse/refusal segment và validator budget exhaustion.
- Ingestion và query runtime dùng cùng embedding generation; mismatch fail
  closed và không đọc mixed index.
- Provider request/usage/cost evidence pin request ID, release, price-book
  revision, reserved/incurred units và reconciliation state.
- Runtime không đọc một shared OpenAI credential/evidence bundle cho cả
  generation và embedding; revoke/rotate một capability không làm hỏng capability
  còn lại ngoài policy đã khai báo.
- Integration tests bao phủ restart, provider drift, cancellation, circuit,
  index mismatch và late result; PostgreSQL/pgvector tests không skip.
- Independent AI-safety, security, resilience và cost review có run evidence.
- Coordination Request
  `coord-980ec230-0798-4a3b-858b-b1b7ef6a986e` được phản hồi/đóng bằng contract
  và runtime evidence của AI Knowledge Engineering.

## Checkpoint

Progress hiện tại (chưa commit; xem Evidence):

- Runtime resolve active pointer và immutable release manifest trên từng turn,
  qua PostgreSQL trusted artifact/evidence registry và freshness fence thực.
- Pointer pin activation, candidate digest, activation envelope và revision;
  runtime revalidate sau graph execution để chặn revoke/rollback giữa turn.
- Generation và embedding có credential, project, approval, retention, budget
  và adapter độc lập. Legacy shared OpenAI authority bị từ chối khi cả hai
  capability cùng bật.
- Model, prompt, policy, graph, output schema, embedding generation, retriever,
  knowledge profile, tool registry và grounding validator đều được so khớp
  với artifact digest trong release manifest.
- Retrieval dùng active Knowledge snapshot theo đúng assistant profile, ACL,
  locale và release UUID. Evidence authority kiểm lại pointer trước khi phát
  answer.
- Deterministic extractive grounding baseline chặn citation ngoài evidence,
  số liệu bịa và thay đổi phủ định. Đây là baseline fail-closed; paraphrase
  chỉ được mở khi evaluator đã hiệu chuẩn và được phê duyệt.
- Model Mesh cache có giới hạn và đóng transport khi evict. Startup/shutdown
  dọn tài nguyên theo exception-safe lifecycle; per-turn lease ngăn đóng
  transport đang có request và composition failure luôn trả lease.
- Graph và retriever artifact binding gồm SHA-256 của đúng runtime source bytes,
  không còn chỉ là descriptor/revision do caller khai báo.
- Internal API trả release revision thực và usage/cost thực; lỗi release
  authority được chuẩn hóa thành public `RELEASE_UNAVAILABLE`.
- Final result mang receipt gắn activation, candidate/envelope digest, pointer
  revision, request/session/turn, conversation version và fencing token.
  PostgreSQL AI cấp short-lived commit lease idempotent; active lease chặn
  rollback pointer trong cửa sổ final commit và lease hết hạn được dọn theo
  lô hữu hạn.
- NestJS kiểm strict receipt binding và PostgreSQL lưu toàn bộ provenance cùng
  terminal turn. Partial receipt bị schema/DB constraint từ chối; thời hạn được
  kiểm bằng database clock.
- Integration test mới chạy graph thật qua active PostgreSQL/pgvector snapshot,
  ACL/revision revalidation và citation grounding bằng deterministic test
  adapters. Fixture này là technical evidence, không đại diện Content/Legal
  approval cho nguồn VinFast staging.
- Coordination Request với AI Knowledge Engineering đã được phản hồi và đóng.
- Response authenticity đã được triển khai trong `VFBIZ-0132` bằng detached
  Ed25519 signature bind raw body/request/correlation/TTL. Exact next action:
  hoàn tất independent security review cùng production mTLS evidence, rồi đưa
  một nguồn VinFast được Content/Legal Owner duyệt qua release pipeline.
  Public/staging dispatch tiếp tục bị khóa tới khi các human/security gate và
  browser E2E đạt.

## Evidence

- [x] `npm run verify:ai` / focused static gates — 2026-07-27: Ruff clean,
      Pyright 0 errors; Alembic dry-run applies through `20260727_0015`.
- [x] `VFBIZ_RUN_DB_INTEGRATION=1 uv run pytest tests -q` — 2026-07-27:
      full suite passed with 0 skipped/failed against real PostgreSQL after
      commit-lease and grounded-turn additions.
- [x] `npm run verify:api` — 2026-07-27: 291 unit tests, 67 E2E tests,
      lint/typecheck/Prisma/build passed.
- [x] API isolated PostgreSQL replay — 2026-07-27: all 20 migrations applied;
      38 integration tests passed.
- [x] `npm run governance:check` — 2026-07-27: passed.
