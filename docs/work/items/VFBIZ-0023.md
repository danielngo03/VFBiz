---
id: VFBIZ-0023
title: Approved knowledge-source ingestion pipeline
status: done
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/pyproject.toml
  - backend/ai/uv.lock
  - backend/ai/migrations
  - backend/ai/app/platform/config
  - backend/ai/app/infrastructure/messaging
  - backend/ai/app/infrastructure/object_storage
  - backend/ai/app/workers
  - backend/ai/app/modules/knowledge
  - backend/ai/docs/knowledge-release.md
  - backend/ai/docs/knowledge-ingestion.md
  - backend/ai/tests/fixtures/knowledge
  - backend/ai/tests/unit/knowledge
  - backend/ai/tests/integration/knowledge
  - backend/ai/tests/architecture/test_persistence_models.py
depends_on:
  - VFBIZ-0022
controlled_signals:
  - knowledge-ingestion
  - ai-retrieval
  - data-governance
  - license
  - pii
exclusive_resources:
  - database-migration
  - dependency-lockfile
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 8
review_date: "2026-08-23"
updated_at: "2026-07-24T21:26:51.462Z"
---

# Outcome

Pipeline ingest một approved knowledge source vào candidate namespace bằng
quarantine, scan, parse/chunk/embed và evidence có thể resume; pipeline không tự
activate Knowledge Release.

## Constraints

- Không network download nếu Source Register chưa approved rights/purpose/ACL.
- Source Register là read-only input; ingestion worker không sửa status,
  purpose, ACL hoặc approval evidence.
- Test dùng local synthetic fixture; chưa crawl nội dung VinFast thật khi chưa
  có Content/Legal/Data Owner.
- Không trộn runtime knowledge với evaluation/red-team/training dataset.
- Không ghi customer chat, PII hoặc downloaded binary vào Git.

## Done when

- Allowlisted fetch chặn redirect/MIME/size/checksum bất thường.
- Upload/parser kiểm signature, page/pixel/decompression ceiling; HTTP request
  chỉ tạo job và không parse tài liệu trong request thread.
- Malware/secret/PII/rights scan chạy trước parse/chunk/embed.
- Worker xử lý bounded page/chunk memory; job idempotent/resumable, retry hữu
  hạn, có DLQ và output candidate với lineage đầy đủ.
- Exact/semantic duplicate, deletion/tombstone và partial failure được test.
- Candidate chỉ tạo evidence; approval/activation cần Data Owner và release
  workflow riêng.

## Checkpoint

- Đã triển khai aggregate job/stage/checkpoint, PostgreSQL leased queue dùng
  `SKIP LOCKED`, OCC/fencing, transactional outbox, artifact lineage và migration
  `20260725_0005`.
- Baseline adapter chỉ nhận approved packaged synthetic UTF-8 source, không
  network; signature PDF/archive/image fail closed. Hai scan gate nằm trước parse
  và trước chunk/embed; candidate namespace không chạm active retrieval table.
- Parser dùng continuation cursor, content scan checkpoint theo unit; lease
  heartbeat và worker polling lifecycle ngăn stage dài bị reclaim sai.
- Candidate manifest chứng minh lineage source → parsed unit → chunk → embedding
  bằng committed fence và checkpoint. GCS/Pub/Sub/Document AI vẫn cần typed
  config, workload identity và provider acceptance trước khi bật.
- Exact next action: VFBIZ-0024 triển khai API–AI transport và cancellation
  propagation; production ingestion adapter không được bật từ baseline local.

## Evidence

- [x] `npm run verify:ai` — Ruff, Pyright, 133 passed/2 skipped và Alembic SQL đạt
- [x] PostgreSQL 17 integration — 2 passed; `alembic check` không có drift
- [x] Independent architecture/risk review vòng cuối — không còn P0/P1 sau fix
- [x] `npm run governance:check` — đạt sau khi sinh lại canonical views
