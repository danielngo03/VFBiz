---
id: VFBIZ-0075
title: Bộ báo cáo kiến trúc đích VFBiz
status: review
mode: controlled
priority: P1
owner_team: architecture-integration
accountable_role: architect
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - reports/common
  - docs/decisions/0007-ev-route-and-charging-planner.md
  - docs/work/items/VFBIZ-0075.md
  - docs/INDEX.md
  - docs/INDEX.json
  - tools/reports.mjs
  - package.json
  - package-lock.json
  - WORK.md
depends_on: []
controlled_signals:
  - architecture
  - cross-system
  - dependency-policy
  - documentation
exclusive_resources:
  - dependency-lockfile
required_checks:
  - npm run reports:check
  - npm run governance:check
revision: 4
review_date: "2026-10-24"
updated_at: "2026-07-24T11:58:03.566Z"
---

# Outcome

Lãnh đạo và đội kỹ thuật có một bộ báo cáo tiếng Việt, dễ đọc và có hình kiến
trúc deterministic để hiểu kiến trúc đích VFBiz mà không biến report thành
nguồn sự thật cạnh tranh với Product docs, ADR, contracts hoặc workspace docs.

## Constraints

- Report chỉ mô tả kiến trúc đích; không tuyên bố capability đã được triển khai.
- Nội dung phải phân biệt đúng authority của Drupal, Keycloak, API, AI,
  Customer Portal, Workforce Portal, Mobile và external systems.
- Chatbot không được hứa zero hallucination; EV Planner baseline không được mô
  tả như live navigation hoặc vehicle telemetry.
- Sơ đồ dùng Mermaid source và SVG tự chứa, không dùng remote asset/font/CDN
  hoặc brand asset chưa được phê duyệt.
- Bảo toàn toàn bộ thay đổi ngoài allowed paths, đặc biệt WIP Customer Portal.

## Done when

- `reports/common` có index, chín báo cáo target-architecture, chín Mermaid
  source và chín SVG tương ứng.
- ADR EV Route & Charging Planner ghi rõ phạm vi pre-trip, authority dữ liệu,
  provider boundary và các lựa chọn bị trì hoãn.
- Report metadata, source links, internal links, alt text và accessibility
  metadata của diagram đều được kiểm deterministic.
- `npm run reports:check` và `npm run governance:check` đạt mà không sửa file
  generated ngoài phạm vi.

## Checkpoint

- Base revision: `74c8f0e`; unrelated dirty path:
  `apps/customer-portal/next-env.d.ts`.
- Added ADR 0007, 10 report pages, 9 Mermaid sources, 9 self-contained SVGs,
  source-drift manifest and deterministic build/check tooling.
- Mermaid CLI is pinned at `11.16.0`; ELK layout was selected after visual QA
  to avoid unusable ultra-wide diagrams.
- Exact next action: Architecture/Product/Security review the target report set.

## Evidence

- [x] `npm run reports:check` — validated 10 reports and 9 deterministic,
      accessible diagrams with no stale SVG or canonical-source drift.
- [x] `npm run governance:check` — current docs index, report drift,
      authorization catalog, 72 work items and 61 context scenarios passed.
- [x] `npm run test:governance` — adapters, agent control, work control,
      governance and all four OpenAPI contracts passed.
- [x] Visual QA — System Landscape, Chatbot Runtime and EV Planner were rendered
      to PNG previews; ELK output is readable without clipped labels or remote
      assets.
- [x] `git diff --check` and `node --check tools/reports.mjs` — passed.
- [ ] Human review — Product Owner, Architect, Security Owner and
      Customer/Workforce Experience representatives.

## Residual risks

- `npm audit` reports seven high findings in existing NestJS/Prisma/Next
  dependency paths. None is introduced through `@mermaid-js/mermaid-cli`; they
  require separate runtime dependency work and were not force-updated here.

### ready — 2026-07-24T11:46:44.394Z

Architecture report acceptance and EV Planner ADR are defined.

### active — 2026-07-24T11:46:44.694Z

Begin reports/common content, diagrams and deterministic report tooling.

### review — 2026-07-24T11:58:03.566Z

Report content, diagrams and deterministic checks are complete; awaiting named human architecture/product/security/experience review.
