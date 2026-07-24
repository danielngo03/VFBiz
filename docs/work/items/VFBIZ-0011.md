---
id: VFBIZ-0011
title: Chuẩn hóa tri thức Chatbot V6 và Dataset Factory
status: done
mode: controlled
priority: P0
owner_team: architecture-integration
accountable_role: architect
primary_workspace: root
affected_workspaces:
  - root
  - api
  - ai
allowed_paths:
  - .agents
  - .claude
  - .codex
  - .gemini
  - backend/api/AGENTS.md
  - backend/api/docs
  - backend/api/src/app.module.ts
  - backend/api/src/modules
  - backend/ai/AGENTS.md
  - backend/ai/.agents
  - backend/ai/.claude
  - backend/ai/app/modules
  - backend/ai/docs
  - backend/ai/tests
  - contracts/ai
  - docs
  - tests/governance
  - tools
  - WORK.md
depends_on: []
controlled_signals:
  - architecture
  - ai-dataset
  - ai-evaluation
  - data-governance
  - license
exclusive_resources:
  - agent-organization-registry
  - ai-dataset-registry
required_checks:
  - npm run governance:check
  - npm run verify:api
  - npm run verify:ai
plan: docs/work/plans/VFBIZ-0011.md
revision: 3
review_date: "2026-08-23"
updated_at: "2026-07-23T05:07:26.176Z"
---

# Outcome

VFBiz có nguồn tri thức Chatbot V6 bền vững, routing đúng theo rủi ro, tổ chức
team rõ ràng và Dataset Factory có contract, skill, role cùng quality gate đủ để
agent khác tiếp tục mà không đọc toàn bộ repository.

## Constraints

- Không phát triển thêm business feature hoặc thay đổi public `/api/v1`.
- Không tải dataset, crawl nội dung VinFast hay dùng production/customer data.
- Human Data, Legal, Privacy, Security và Release Owner giữ quyền phê duyệt.
- Provider adapter chỉ là lớp tương thích; business rule nằm trong nguồn canonical.
- Chỉ sửa runtime composition để loại module NestJS hoàn toàn rỗng, không xóa
  capability khỏi roadmap.

## Done when

- Product, architecture và ADR Chatbot V6 là nguồn active; staging Account/Trip
  cũ được đánh dấu superseded.
- API/AI workspace có tài liệu đúng boundary và nested instructions chọn lọc.
- Routing phân biệt engagement, mobility, assistant, inference, knowledge,
  assurance và data governance.
- Dataset source thiếu quyền bị chặn trước network; generator không thể tự release.
- Bảy schema dataset/AI release hợp lệ và synthetic fixture nhỏ vượt validator.
- Skill dataset vượt quick validation cùng positive/negative realistic scenarios.
- Instruction chain dưới 16 KiB và toàn bộ governance/API/AI gate exit `0`.
- Generated index và provider adapters không drift.

## Decisions and assumptions

- Đợt đầu tập trung evaluation/red-team; chưa có SFT release.
- Mục tiêu quy mô là 500–1.000 gold cases và 10.000–30.000 synthetic candidates,
  không phải số record được tự động release.
- Public dataset chỉ được đăng ký candidate; Dataset Card không thay Legal review.

## Checkpoint

- Base revision: `1310d7529dbc9a275b7fcef1b66b55e2b285b858`.
- Branch: `agent/VFBIZ-0005`; thay đổi chưa phải production release.
- Changed paths: root product/architecture/ADR/governance, API/AI docs và nested
  instructions, agent organization/adapters, Dataset Factory contracts/skills/tests,
  context resolver/scenarios và NestJS composition cleanup.
- Blocker: không có blocker kỹ thuật. Mọi public source candidate vẫn ở
  `legal-hold` hoặc `rejected`; chưa có dataset nào được download/release.
- Exact next action: Product/Data/Security/Legal owner review V6 scope và cấp
  work item implementation riêng cho conversation runtime/graph.

## Evidence

- [x] `npm run governance:check` — 33 provider-neutral routing scenarios,
  instruction/role/skill/schema/work validation đều đạt.
- [x] `npm run verify:api` — lint, typecheck, 32 unit + 12 E2E, Prisma validate
  và Nest build đều đạt.
- [x] `npm run verify:ai` — Ruff, Pyright, 25 Pytest và Alembic SQL dry-run đều đạt.
- [x] `skill-creator quick_validate` — 11/11 project skill hợp lệ; metadata
  `agents/openai.yaml` được sinh bằng script chính thức.
- [x] Dataset realistic tests — positive/negative validation, cross-shard
  duplicate, candidate manifest và download-rights gate đều đạt.
- [x] `git diff --check` — không có whitespace error.

Residual risk: đây là architecture/governance foundation. V6 runtime,
production capacity, external dataset rights và VinFast factual content vẫn cần
work item/evidence/human approval riêng.

### review — 2026-07-23T05:07:25.899Z

Independent gates đã đạt; không có dataset download hoặc production release.

### done — 2026-07-23T05:07:26.176Z

Hoàn tất repository knowledge, routing và Dataset Factory foundation; residual runtime work được tách riêng.
