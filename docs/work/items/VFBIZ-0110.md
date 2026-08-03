---
id: VFBIZ-0110
title: Execute approved Vietnamese retrieval bake-off
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
  - backend/ai/docs/evaluation-and-release.md
  - docs/work/items/VFBIZ-0110.md
  - WORK.md
depends_on:
  - VFBIZ-0103
  - VFBIZ-0108
  - VFBIZ-0111
controlled_signals:
  - ai-retrieval
  - ai-release
  - grounding
exclusive_resources:
  - ai-release-evidence
required_checks:
  - npm run verify:ai
  - npm run verify:ai:integration
  - npm run governance:check
revision: 2
review_date: "2026-07-25"
---

# Outcome

Release Owner có evidence so sánh managed và self-host embedding/reranker
candidates trên cùng VinFast-approved Vietnamese held-out suite trước khi chọn
production candidate.

## Constraints

- Data Owner phải phê duyệt provenance và held-out split trước khi chạy.
- Không dùng public leaderboard hoặc synthetic fixture làm production evidence.
- Cùng query suite, retrieval contract, hardware profile và cost normalization
  được dùng cho mọi candidate.
- Candidate không đạt citation/refusal hoặc security gate không được bù bằng
  latency hay giá rẻ.
- Một `RetrievalBakeoffManifest` tự kiểm chứng chỉ chứng minh tính toàn vẹn
  canonical. Trước khi chạy hoặc dùng kết quả cho release, phải có
  `RetrievalSuiteAuthority` độc lập bind đúng suite/source/index/evaluator
  digest, provenance evidence, held-out flag và ba subject khác nhau. Agent
  không được tự tạo hoặc thay thế authority record.

## Done when

- Coverage gate của VFBIZ-0107 đạt trên approved suite.
- Vertex/OpenAI/self-host candidates được đo cùng Recall@5/20, nDCG@10, MRR,
  reranker lift, p50/p95, throughput và normalized cost.
- Báo cáo pin model/revision/dimension/instruction digest, index generation,
  corpus hash, hardware/region và evaluator revision.
- Release Owner chọn hoặc từ chối candidate bằng signed evaluation evidence;
  không adapter nào tự promote.

## Checkpoint

- Exact next action: chờ VFBIZ-0103 provider adapters và VFBIZ-0108 versioned
  index generation hoàn tất, sau đó nạp approved held-out suite.

## Evidence

- [ ] `npm run verify:ai` — add evidence reference
- [ ] `npm run verify:ai:integration` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
