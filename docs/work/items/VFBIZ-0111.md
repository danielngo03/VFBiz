---
id: VFBIZ-0111
title: Adopt versioned embedding generations in Knowledge runtime
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
  - docs/work/items/VFBIZ-0111.md
  - WORK.md
depends_on:
  - VFBIZ-0108
controlled_signals:
  - ai-retrieval
  - migration
  - ai-release
exclusive_resources:
  - ai-retrieval-contract
required_checks:
  - npm run verify:ai
  - npm run verify:ai:integration
  - npm run governance:check
revision: 6
review_date: "2026-07-25"
updated_at: "2026-07-25T16:02:01.468Z"
---

# Outcome

Knowledge runtime materialize và retrieve qua immutable embedding index
generation, cho phép active và candidate generation khác dimension tồn tại song
song mà không trộn revision.

## Constraints

- Chỉ dùng schema do VFBIZ-0108 tạo; không phát sinh DDL từ provider input.
- Active release tiếp tục phục vụ trong khi candidate backfill.
- Không pad/truncate vector; dimension mismatch fail closed.
- Cutover chỉ thông qua governed Knowledge Release pointer và evaluation
  evidence.

## Done when

- SQLAlchemy model không còn `Vector(1536)` global.
- Materialization pin generation ID/revision/dimension và checksum.
- Retrieval query lọc generation trước vector distance; không cross-generation.
- Integration tests chứng minh parallel backfill, active/candidate isolation,
  atomic cutover, rollback và tombstone.

## Checkpoint

- Runtime domain, materialization và retrieval đã pin immutable embedding index
  generation; unit và PostgreSQL Knowledge integration tests đạt.
- Coordination Request đã giao architecture inventory cho AI Platform
  Foundation qua VFBIZ-0113 và lane đó đã hoàn tất.
- Exact next action: VFBIZ-0112 có thể contract `NOT NULL` sau khi rollout
  runtime được xác minh trên staging.

## Evidence

- [x] `npm run verify:ai` — 199 passed; 4 explicitly separated DB tests
- [x] `npm run verify:ai:integration` — 17 PostgreSQL integration tests passed
- [x] `npm run governance:check` — 110 work items and 61 context scenarios passed
