---
id: VFBIZ-0076
title: README giới thiệu repository VFBiz
status: review
mode: bounded
priority: P2
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - README.md
  - docs/work/items/VFBIZ-0076.md
  - WORK.md
  - docs/INDEX.md
  - docs/INDEX.json
depends_on: []
controlled_signals: []
exclusive_resources: []
required_checks:
  - README format
  - README links
  - governance
revision: 4
review_date: "2026-10-24"
updated_at: "2026-07-24T12:12:58.670Z"
---

# Outcome

Người đọc GitHub hiểu được mục tiêu, kiến trúc, cấu trúc repository, trạng thái
hiện tại, cách bắt đầu và nơi tìm nguồn tài liệu chuẩn của VFBiz từ root README.

## Constraints

- Chỉ tổng hợp từ source, tài liệu active và báo cáo kiến trúc đã có.
- Không tuyên bố roadmap capability là đã triển khai hoặc production-ready.
- Không thêm badge, logo, asset hoặc liên kết thương hiệu chưa được phê duyệt.
- Không thay đổi runtime, contract hoặc quyết định kiến trúc.

## Done when

- README có phần giới thiệu, kiến trúc, workspace map, technology stack,
  quick start, quality gates, documentation map và contribution workflow.
- Sơ đồ dùng asset nội bộ trong `reports/common` và hiển thị được trên GitHub.
- Mọi liên kết repository trong README trỏ tới file đang tồn tại.
- Định dạng và governance checks đạt.

## Checkpoint

- Đã xác minh repository blueprint, báo cáo điều hành và báo cáo kiến trúc.
- README đã được viết lại, dùng hai sơ đồ nội bộ và phân biệt rõ nền tảng,
  nghiệm thu và roadmap.
- Exact next action: engineering lead review nội dung trước khi publish GitHub.

## Evidence

- [x] `README format` — Prettier và `git diff --check` đạt ngày 24/07/2026.
- [x] `README links` — 19 liên kết nội bộ được xác minh tồn tại.
- [x] `governance` — docs, reports, capability, work schema, provider adapter,
      skill và 61 context scenario đều đạt.

### ready — 2026-07-24T12:11:16.706Z

Scope và acceptance đã được khóa từ repository blueprint và reports/common.

### active — 2026-07-24T12:11:16.983Z

Bắt đầu viết root README; chỉ thay tài liệu và generated work/index views.

### review — 2026-07-24T12:12:58.670Z

README code-complete; format, 19 local links và governance checks đạt. Chờ engineering lead review trước khi publish GitHub.
