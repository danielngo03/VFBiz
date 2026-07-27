---
id: VFBIZ-0030
title: Public Account contract parity
status: done
mode: controlled
priority: P0
owner_team: architecture-integration
accountable_role: architect
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - contracts/openapi
  - backend/api/test/contract
depends_on:
  - VFBIZ-0028
  - VFBIZ-0029
controlled_signals:
  - architecture
  - public-contract
exclusive_resources:
  - public-contract
required_checks:
  - npm run contracts:lint
  - npm run governance:check
revision: 5
review_date: "2026-08-23"
updated_at: "2026-07-24T17:18:01.702Z"
---

# Outcome

Reviewed OpenAPI chỉ công bố capability Account đang chạy thật và có conformance
evidence; BFF route không bị mô tả nhầm như API Platform route.

## Constraints

- Breaking removal/version change cần ADR hoặc compatibility plan.
- Không tạo placeholder endpoint chỉ để khớp YAML.
- Generated SDK là derived artifact; source of truth vẫn là reviewed OpenAPI.
- Contract writer giữ exclusive lease.

## Done when

- `/auth/customer/*` được đặt đúng BFF boundary hoặc loại khỏi API contract.
- `/api/v1/me/sessions` chỉ active khi VFBIZ-0029 có runtime evidence.
- Runtime-vs-reviewed contract test phát hiện operation thừa/thiếu.
- OpenAPI lint không warning và compatibility gate đạt.

## Checkpoint

- Human authority đã duyệt route inventory/parity evidence ngày 25/07/2026.
  Mọi thay đổi Account public contract tiếp theo vẫn phải giữ exclusive lease.

## Evidence

- [x] `npm run contracts:lint` — Public/Internal OpenAPI hợp lệ, không warning;
  runtime schema check đạt ngày 23/07/2026.
- [x] `npm run governance:check` — work schema, instruction/role/skill và 55
  provider-neutral context scenarios đạt ngày 23/07/2026.
- [x] `npm run verify:api` — Account runtime-versus-reviewed inventory test,
  137 unit tests, 47 E2E tests, lint/typecheck/Prisma/build đạt ngày
  23/07/2026.
- [x] Architect approval — người dùng phê duyệt rõ `VFBIZ-0030` ngày
  25/07/2026.

### ready — 2026-07-23T11:21:59.819Z

Dependency Account/Garage/Session đã hoàn tất; bắt đầu runtime-versus-reviewed contract parity.

### active — 2026-07-23T11:22:00.151Z

So sánh operation inventory Account theo operationId; không sửa runtime trong lane contract.

### review — 2026-07-23T11:25:12.264Z

Account Authentication/Customer/Garage runtime-versus-reviewed parity, OpenAPI lint và API verification đã đạt; chờ Architect review.
