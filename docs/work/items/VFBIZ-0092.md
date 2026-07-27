---
id: VFBIZ-0092
title: Customer AI operator guides and configuration catalog
status: done
mode: bounded
priority: P1
owner_team: ai-assistant-orchestration
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
  - ai
  - api
allowed_paths:
  - guides
  - package.json
  - tools/guides-check.mjs
  - backend/ai/.env.example
depends_on: []
controlled_signals:
  - ai-assistant
exclusive_resources: []
required_checks:
  - npm run guides:check
  - npm run governance:check
revision: 5
review_date: "2026-07-25"
updated_at: "2026-07-25T07:23:00.720Z"
---

# Outcome

Một operator mới có thể cấu hình local baseline và hiểu chính xác các gate để
triển khai Customer AI Assistant trên GCP mà không đưa secret vào Git, không
nhầm Google IAM với customer identity và không bật adapter chưa có typed config.

## Constraints

- Guide là operational aid; ADR, contract và typed runtime config vẫn là nguồn
  chuẩn.
- Không ghi secret thật, project ID thật, production endpoint hoặc dữ liệu
  VinFast chưa được phê duyệt.
- Chỉ tài liệu hóa environment variable đã được schema/config kiểm tra.
- EV Journey Planner và Google Maps nằm ngoài phạm vi.

## Done when

- Có catalog ở `guides/README.md` và lộ trình đọc Customer AI không stale.
- GCS, Pub/Sub, Document AI, DLQ, IAM, DSAR, checkpoint/resume, key rotation và
  service assertion/JWKS rotation có runbook/gate rõ.
- Human approval guide phản ánh VFBIZ-0030/0032 đã được duyệt.
- `guides:check` kiểm internal link, secret placeholder, duplicate title và
  environment variable chưa được typed config hỗ trợ.

## Checkpoint

- Đã thêm catalog, GCP ingestion/DLQ/IAM runbook, checkpoint/key rotation/DSAR
  drill và typed environment validation.
- Exact next action: VFBIZ-0024 bổ sung typed API–AI transport config; guide chỉ
  được cập nhật theo contract đã merge, không dự đoán tên biến.

## Evidence

- [x] `npm run guides:check` — 12 guide documents, links và typed AI env đạt
- [x] `npm run governance:check` — 89 work items và 61 context scenarios đạt
