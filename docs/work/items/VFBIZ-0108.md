---
id: VFBIZ-0108
title: Versioned embedding index schema migration
status: done
mode: controlled
priority: P0
owner_team: ai-platform-foundation
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/migrations
  - backend/ai/tests/architecture
  - backend/ai/tests/contract
  - docs/work/items/VFBIZ-0108.md
  - WORK.md
depends_on:
  - VFBIZ-0107
controlled_signals:
  - migration
  - ai-retrieval
  - ai-release
exclusive_resources:
  - database-migration
required_checks:
  - npm run verify:ai
  - npm run verify:ai:integration
  - npm run governance:check
revision: 6
review_date: "2026-07-25"
updated_at: "2026-07-25T15:48:09.420Z"
---

# Outcome

PostgreSQL/pgvector lưu nhiều embedding index generation có dimension/revision
độc lập, cho phép backfill và atomic release cutover mà không khóa schema vào
`Vector(1536)`.

## Constraints

- Migration phải online-safe, rollback rõ và không rewrite active corpus trong
  request path.
- Đây là expand phase: generation columns tạm nullable để runtime cũ tiếp tục
  phục vụ; VFBIZ-0111 backfill/adopt và VFBIZ-0112 mới bật contract `NOT NULL`.
- Không dùng untyped array, pad/truncate vector hoặc dynamic SQL từ provider
  input.
- Mỗi index generation có immutable embedding revision, dimension, metric,
  normalization, tokenizer/instruction digest và lifecycle.
- Active pointer chỉ chuyển sau materialization checksum và evaluation evidence.

## Done when

- Schema không còn hard-code một vector dimension cho mọi release.
- Schema có immutable index-generation identity, embedding revision, dimension,
  metric, normalization và instruction digest.
- Legacy 1.536-dimension rows được backfill vào một generation rõ ràng mà không
  thay active release pointer.
- Chunk/release không thể tham chiếu generation sai revision hoặc dimension.
- Migration upgrade/downgrade và static architecture contract đạt; runtime
  adoption, concurrent cutover, rollback và tombstone thuộc VFBIZ-0111.

## Checkpoint

- Exact next action: bắt đầu sau VFBIZ-0107 contract; chọn physical schema qua
  migration ADR/test, không chọn dimension/model bằng phỏng đoán.

## Evidence

- [x] `npm run verify:ai` — Ruff/Pyright/Alembic đạt; 198 tests passed.
- [x] `npm run verify:ai:integration` — 17 PostgreSQL integration tests passed
      sau migration 0009.
- [x] `npm run governance:check` — 108 work items và 61 provider-neutral
      scenarios passed cùng docs/reports/guides/authorization checks.

### migration evidence — 2026-07-25

- Isolated PostgreSQL 17 + pgvector upgrade → downgrade → upgrade đạt.
- Seeded legacy release/chunk được backfill cùng generation ID, revision và
  dimension; active pointer không bị thay đổi.
- Downgrade guard từ chối non-legacy dimension thay vì truncate/pad dữ liệu.
- Integration gate phát hiện contract `NOT NULL` quá sớm; migration được sửa
  thành expand phase trước khi commit.
