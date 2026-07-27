---
id: VFBIZ-0101
title: Workforce Knowledge Management API
status: proposed
mode: controlled
priority: P0
owner_team: customer-engagement
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
  - ai
allowed_paths:
  - backend/api/src/modules/engagement
  - backend/api/prisma/models/engagement.prisma
  - backend/api/prisma/migrations
  - backend/api/test/e2e/engagement
  - backend/api/test/integration/engagement
  - backend/api/docs/conversation-runtime.md
  - backend/api/docs/ai-gateway-and-tools.md
  - contracts/openapi
depends_on:
  - VFBIZ-0025
controlled_signals:
  - knowledge-release
  - data-governance
  - authorization
  - pii
  - public-contract
  - migration
exclusive_resources:
  - ai-knowledge-release-registry
  - public-contract
  - database-migration
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 1
review_date: "2026-07-25"
---

# Outcome

NestJS cung cấp Workforce-only API để quản lý knowledge source, signed upload,
ingestion job, simulator, release request/approval/activation/rollback và audit;
mọi operation được capability/scope/maker-checker enforce và gọi private AI
control plane qua signed contract.

## Constraints

- Keycloak chỉ xác thực workforce; capability và object scope do API quyết định.
- Binary lớn đi thẳng object-storage quarantine bằng short-lived signed upload,
  không proxy qua NestJS hoặc Workforce Portal.
- API không parse/embed tài liệu và không tự approve AI release.
- Không trả signed locator, raw document text, secret, customer PII hoặc internal
  provider error cho browser.
- Candidate author không được approve/activate chính candidate của mình.

## Done when

- Workforce OpenAPI tách khỏi customer contract và có source/revision/job/
  simulator/change-request/release/audit resources với response đầy đủ.
- Atomic business workflow lưu reason, actor, entitlement revision, correlation,
  OCC/idempotency và transactional outbox trước khi gọi private AI.
- Capability, organizational scope, step-up MFA, maker-checker, last-safe-release
  và emergency withdrawal được enforce deny-by-default.
- Private AI assertion pin source/release/policy revision; callback/webhook có
  signature, replay protection, reconciliation, retry hữu hạn và DLQ.
- Malicious MIME, oversized/decompression bomb, stale version, duplicate,
  self-approval, cross-scope và AI/object-storage outage đạt integration/E2E.

## Checkpoint

- Exact next action: khóa Workforce OpenAPI và private Knowledge Control contract
  sau VFBIZ-0025; giữ migration/contract lease duy nhất trong lane này.

## Evidence

- [ ] `npm run verify:api` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
