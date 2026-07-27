---
id: VFBIZ-0097
title: Workforce Knowledge Hub operations
status: proposed
mode: controlled
priority: P0
owner_team: workforce-experience
accountable_role: engineering-lead
primary_workspace: workforce-portal
affected_workspaces:
  - workforce-portal
allowed_paths:
  - apps/workforce-portal/src/app
  - apps/workforce-portal/src/features
  - apps/workforce-portal/tests
  - apps/workforce-portal/docs
depends_on:
  - VFBIZ-0101
controlled_signals:
  - knowledge-release
  - data-governance
  - authorization
  - pii
  - workforce-portal
exclusive_resources: []
required_checks:
  - npm run governance:check
  - npm run verify:apps
  - npm run verify:api
revision: 1
review_date: "2026-07-25"
---

# Outcome

Nhân sự được cấp capability có thể quản lý source/revision, theo dõi ingestion,
chạy simulator, submit/approve/activate/rollback Knowledge Release và xem audit
mà không truy cập Cloud Console.

## Constraints

- Capability nguyên tử, organizational scope, maker-checker và MFA step-up là
  enforcement tại NestJS; UI ẩn nút không phải security boundary.
- Upload dùng signed URL/quarantine; portal không proxy binary lớn qua Node.
- Candidate author không tự approve/activate; human authority giữ release.
- Không hiển thị secret, raw PII, signed locator hoặc untrusted document HTML.

## Done when

- Source list/detail, revision diff, ingestion job/error, candidate evaluation,
  simulator citation highlight, approval inbox, activation/rollback và audit UI.
- Upload/fetch/parse progress asynchronous; resume/DLQ/retry hữu hạn hiển thị rõ.
- Critical revision barrier và emergency withdrawal có warning/confirmation.
- Cross-role/scope denial, self-approval, stale OCC, malicious file, provider
  outage và rollback được E2E.
- Browser không có cloud credential; API audit ghi actor/reason/revision/
  correlation nhưng không ghi document content thừa.

## Checkpoint

- Exact next action: khóa Workforce API contract/capability catalog sau
  VFBIZ-0101; portal chỉ dùng generated client và không sửa API trong cùng lane.

## Evidence

- [ ] `npm run governance:check` — add evidence reference
- [ ] `npm run verify:apps` — add evidence reference
- [ ] `npm run verify:api` — add evidence reference
