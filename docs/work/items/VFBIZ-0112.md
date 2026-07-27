---
id: VFBIZ-0112
title: Enforce embedding generation contract after runtime cutover
status: done
mode: controlled
priority: P0
owner_team: ai-platform-foundation
accountable_role: release-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/migrations
  - backend/ai/tests/architecture
  - backend/ai/tests/contract
  - docs/work/items/VFBIZ-0112.md
  - WORK.md
depends_on:
  - VFBIZ-0111
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
revision: 5
review_date: "2026-07-25"
updated_at: "2026-07-25T16:05:38.311Z"
---

# Outcome

Sau khi Knowledge runtime đã cutover, PostgreSQL từ chối mọi release/chunk thiếu
embedding generation và hoàn tất expand–migrate–contract rollout không downtime.

## Constraints

- Chỉ chạy sau VFBIZ-0111 và preflight xác nhận không còn legacy NULL.
- Không tự tạo generation từ provider input.
- Contract migration fail closed nếu backfill chưa hoàn tất.
- Downgrade không được làm mất vector hoặc đổi active release pointer.

## Done when

- Preflight đếm zero release/chunk thiếu generation.
- `index_generation_id` và chunk `embedding_dimension` trở thành `NOT NULL`.
- Integration tests chứng minh legacy insert bị từ chối, governed insert/cutover
  vẫn đạt và rollback schema không mất dữ liệu.

## Checkpoint

- Preflight fail-closed, `NOT NULL` contract và schema-only downgrade đã được
  kiểm chứng trên PostgreSQL 17 + pgvector.
- Exact next action: VFBIZ-0103 có thể triển khai provider adapters trên
  generation contract đã khóa.

## Evidence

- [x] `npm run verify:ai` — 201 passed; 4 DB tests separated by explicit gate
- [x] `npm run verify:ai:integration` — 17 PostgreSQL integration tests passed
- [x] `npm run governance:check` — 110 work items and 61 scenarios passed
