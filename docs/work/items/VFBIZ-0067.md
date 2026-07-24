---
id: VFBIZ-0067
title: Chuẩn hóa product, tài liệu và ownership của Customer Portal
status: done
mode: controlled
priority: P0
owner_team: product-management
accountable_role: product-owner
primary_workspace: root
affected_workspaces:
  - root
  - customer-portal
  - mobile
allowed_paths:
  - docs/product
  - docs/architecture
  - docs/decisions
  - docs/work/items/VFBIZ-0067.md
  - apps/customer-portal/README.md
  - apps/customer-portal/docs
  - apps/customer-portal/AGENTS.md
  - .agents/organization.json
  - README.md
  - WORK.md
depends_on: []
controlled_signals:
  - customer-data
  - customer-journey
exclusive_resources:
  - organization-registry
required_checks:
  - npm run docs:check
  - npm run governance:check
revision: 3
review_date: "2026-08-24"
updated_at: "2026-07-24T08:01:20.646Z"
---

# Outcome

Customer Portal có product scope, ADR, ownership và local documentation rõ,
không mâu thuẫn với roadmap hoặc trộn implementation detail vào root.

## Constraints

- Không thay đổi runtime hoặc public API.
- Root chỉ giữ product truth và cross-system decisions; implementation detail nằm tại portal.
- Không tạo thêm tài liệu hoặc role nếu chưa có consumer và owner thực tế.

## Done when

- Product document mô tả audience, journeys, acceptance, KPI và non-goals.
- ADR khóa Next.js BFF, server-only token vault, DAL và contract boundary.
- Team web và mobile được tách với ownership không chồng nhau.
- Root/local docs và instructions tuân thủ context budget.

## Checkpoint

- Product document, ADR 0005, root architecture/product alignment and split web/mobile ownership are complete.
- Customer Portal local documentation is reduced to the three approved durable documents.
- Exact next action: Product Owner reviews material journey/design-system changes during delivery.

## Evidence

- [x] Product/Architecture review completed against the approved plan.
- [x] `npm run docs:check` passed with 64 indexed documents.
- [x] `npm run governance:check` passed with 60 provider-neutral context scenarios.
