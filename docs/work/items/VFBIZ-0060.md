---
id: VFBIZ-0060
title: Workforce authorization security and E2E release evidence
status: proposed
mode: controlled
priority: P0
owner_team: architecture-integration
accountable_role: security-owner
primary_workspace: root
affected_workspaces:
  - root
  - api
  - workforce-portal
  - infra
allowed_paths:
  - tests
  - docs/governance
  - docs/work/items/VFBIZ-0060.md
  - docs/work/plans/VFBIZ-0055.md
  - output/playwright
depends_on:
  - VFBIZ-0058
  - VFBIZ-0059
controlled_signals:
  - authorization
  - production
exclusive_resources: []
required_checks:
  - npm run verify
revision: 2
review_date: "2026-08-24"
updated_at: "2026-07-24T20:10:00.000+07:00"
---

# Outcome

Threat model, negative authorization, browser E2E và shadow evidence chứng minh
dynamic authorization không tạo privilege escalation hoặc cross-scope access.

## Constraints

- Reviewer read-only; agent không accept residual risk.
- Không dùng production workforce identity hoặc PII trong fixture.

## Done when

- Threat model bao phủ BFF, token vault, authorization API, cache và admin UX.
- Backend/portal/E2E exit gate đạt.
- Named human Security/Release Owner còn là production gate.

## Checkpoint

- Threat model đã được tạo ở trạng thái `proposed`; human Security Owner chưa
  duyệt residual risk.
- Dependency audit ngày 24/07/2026 ghi nhận 7 high advisory trong transitive
  dependencies của NestJS/Fastify, Prisma và Next.js. `npm audit` chỉ đề xuất
  downgrade không phù hợp nên không tự động sửa.
- Chờ VFBIZ-0058, durable idempotency, invalidation transport, shadow parity và
  capability cutover.

## Evidence

- [ ] Full verification and independent review.
- [ ] Upstream dependency patches hoặc time-bound Security exception.
