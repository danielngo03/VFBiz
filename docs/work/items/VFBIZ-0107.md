---
id: VFBIZ-0107
title: Enterprise retrieval contract and Vietnamese bake-off gate
status: done
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/modules/knowledge
  - backend/ai/tests/unit/knowledge
  - backend/ai/tests/integration/knowledge
  - backend/ai/docs/knowledge-release.md
  - docs/work/items/VFBIZ-0107.md
  - WORK.md
depends_on:
  - VFBIZ-0025
controlled_signals:
  - ai-retrieval
  - ai-release
  - grounding
exclusive_resources:
  - ai-retrieval-contract
required_checks:
  - npm run verify:ai
  - npm run verify:ai:integration
  - npm run governance:check
revision: 6
review_date: "2026-07-25"
updated_at: "2026-07-25T15:37:51.282Z"
---

# Outcome

Knowledge Engineering có retrieval contract versioned và gate tiếng Việt
deterministic trước khi provider bake-off hoặc production index được kích hoạt.

## Constraints

- ACL, assistant profile, locale, active release và deletion fence phải lọc
  trước ANN/lexical ranking và được kiểm lại trước khi trả evidence.
- Không đọc một page chunk theo UUID rồi ranking trong Python.
- Không trộn vector từ hai embedding revision trong cùng searchable index.
- Benchmark dùng held-out VinFast-approved cases; public leaderboard chỉ là
  tín hiệu tham khảo.
- Query, hard negative và failure example có PII phải redacted/pseudonymized.

## Done when

- Contract tách `EmbeddingProvider`, lexical/vector candidate source,
  fusion/RRF và bounded reranker; mọi result pin exact release revisions.
- PostgreSQL query thực hiện ACL/release filter cùng FTS và pgvector ANN trước
  khi lấy bounded top-K về application.
- Bake-off gate từ chối suite thiếu tiếng Việt có dấu/không dấu, typo, slang,
  code-switch, tên VF model, numeric policy, ambiguous query,
  stale/contradictory source, hard negative hoặc refusal.
- Summary contract đo Recall@5/20, nDCG@10, MRR, reranker lift,
  citation/refusal correctness, p50/p95 latency, throughput và normalized cost.
- Index generation/cutover thuộc VFBIZ-0108; provider bake-off thật thuộc
  VFBIZ-0110 và không được dùng fixture tự xưng là VinFast-approved.

## Checkpoint

- Exact next action: independent verifier review bounded reranker, query-aware
  PostgreSQL selection và bake-off metric/coverage gate.

## Evidence

- [x] `npm run verify:ai` — Ruff/Pyright/Alembic đạt; 196 tests passed,
      bốn database tests được chạy riêng bởi fail-closed integration gate.
- [x] `npm run verify:ai:integration` — 17 PostgreSQL/pgvector integration
      tests passed trên database đã migrate.
- [x] `npm run governance:check` — docs/reports/guides/authorization,
      106 work items và 61 provider-neutral scenarios passed.

### ready — 2026-07-25T15:13:26.824Z

Provider-neutral retrieval contract and ownership boundary are decision-complete.

### active — 2026-07-25T15:13:26.960Z

Starting with failing retrieval scale and revision-isolation tests.

### implementation — 2026-07-25

- PostgreSQL candidate selection dùng query embedding + FTS trong active
  release/ACL boundary thay vì first-200 UUID page.
- Snapshot resolver, candidate searcher, query embedder và bounded reranker là
  ports độc lập.
- Reranker revision mismatch, outage, duplicate/foreign result đều fail closed.
- Held-out case contract yêu cầu approval digest và bake-off coverage gate;
  metric summary gồm quality, refusal/citation, latency, throughput và cost.
