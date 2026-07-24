---
id: VFBIZ-0005
title: Chuẩn hóa organization model Product, API, AI và Data
status: done
mode: controlled
priority: P1
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - .agents
  - contracts/governance
  - docs/operating-model
  - docs/work
  - docs/INDEX.md
  - docs/INDEX.json
  - tests/governance
  - tools
  - WORK.md
depends_on:
  - VFBIZ-0006
  - VFBIZ-0007
  - VFBIZ-0008
  - VFBIZ-0009
  - VFBIZ-0010
controlled_signals:
  - architecture
  - agent-control
  - ai
  - data-governance
exclusive_resources:
  - agent-organization-registry
required_checks:
  - governance
  - skill-validation
  - provider-parity
  - context-routing
revision: 6
review_date: "2026-08-23"
updated_at: "2026-07-22T18:25:55.587Z"
---

# Outcome

Một agent mới có thể xác định đúng vai trò Product/PM/BA, phòng ban Digital
Platform, AI & Data, team sở hữu path, tài liệu cục bộ và skill cần dùng mà
không nạp toàn bộ docs hoặc tạo thêm runtime agent theo chức danh.

## Constraints

- Không thay đổi runtime API, AI, database schema hoặc public contract.
- Không tạo phòng ban, agent, skill hoặc tài liệu nếu chưa có ownership/path và
  workflow thực tế.
- PO/PM/BA/Data Steward là vai trò tổ chức; chỉ runtime role có tool profile và
  deliverable lặp lại mới trở thành agent adapter.
- Plugin/provider-native skill chỉ là tùy chọn; canonical rule và workflow vẫn
  nằm trong Git.

## Done when

- Mô hình authority phân biệt rõ PO, PM, BA, Data Owner và Data Steward.
- API, AI Knowledge/Data, AI Runtime/Tooling và AI Evaluation/Governance có
  ownership path không chồng lấn và context routing được kiểm thử.
- Docs API/AI nói rõ tài liệu nào thuộc workspace, tài liệu nào thuộc root và
  cách phối hợp khi capability đi qua nhiều team.
- Skill API/AI trỏ đến đúng nguồn kỹ thuật và vượt validator/realistic checks.
- Template WorkItemV2 khớp schema hiện hành.
- Governance, provider parity và context-budget tests đều đạt.

## Checkpoint

- Base revision: `a059cfc`.
- Audit đang thực hiện bằng ba reviewer read-only cho API, AI/Data và hướng dẫn
  Codex chính thức.
- Exact next action: hợp nhất evidence audit thành thay đổi ownership/docs nhỏ
  nhất rồi chạy validation.

## Evidence

- [x] `governance` — `npm run governance:check` đạt: schema, ownership, adapters và 25 scenarios.
- [x] `skill-validation` — 10 root/API/AI skills đều trả `Skill is valid!` từ `quick_validate.py`.
- [x] `provider-parity` — generated Codex/Claude/Gemini adapters vượt governance parity checks; canonical roles không nhân bản business rule.
- [x] `context-routing` — quan sát API Foundation, AI Knowledge, AI Tooling, AI Evaluation và Trip Release đều route đúng team, authority, docs heading và tối đa hai skills.

### active — 2026-07-22T18:09:43.239Z

Organization model, context parser và 23 routing scenarios đã cập nhật; governance pass. Next: triển khai docs/skills cục bộ API và AI bằng hai work item thuộc đúng owner team.
