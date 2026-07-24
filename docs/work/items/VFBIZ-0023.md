---
id: VFBIZ-0023
title: Approved knowledge-source ingestion pipeline
status: proposed
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/modules/knowledge
  - backend/ai/docs/knowledge-release.md
  - backend/ai/docs/knowledge-ingestion.md
  - backend/ai/tests/unit/knowledge
  - backend/ai/tests/integration/knowledge
depends_on:
  - VFBIZ-0022
controlled_signals:
  - knowledge-ingestion
  - ai-retrieval
  - data-governance
  - license
  - pii
exclusive_resources: []
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 1
review_date: "2026-08-23"
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
- Malware/secret/PII/rights scan chạy trước parse/chunk/embed.
- Job idempotent/resumable, output vào candidate namespace với lineage đầy đủ.
- Exact/semantic duplicate, deletion/tombstone và partial failure được test.
- Candidate chỉ tạo evidence; approval/activation cần Data Owner và release
  workflow riêng.

## Checkpoint

- Exact next action: chỉ start sau VFBIZ-0022; dùng một approved synthetic
  source entry và provider-neutral embedding fake.

## Evidence

- [ ] `npm run verify:ai` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
