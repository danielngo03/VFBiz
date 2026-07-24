---
id: VFBIZ-0040
title: NestJS API docs surface, Swagger, Scalar và Vehicle Catalog schema
status: done
mode: controlled
priority: P0
owner_team: api-foundation
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/package.json
  - package-lock.json
  - package.json
  - backend/api/nest-cli.json
  - backend/api/.env.example
  - backend/api/README.md
  - backend/api/src/platform/openapi
  - backend/api/src/platform/config
  - backend/api/src/main.ts
  - backend/api/src/modules/product/presentation
  - backend/api/test/contract
  - backend/api/test/unit/platform/config
depends_on: []
controlled_signals:
  - dependency-policy
  - public-contract
exclusive_resources:
  - root-lockfile
required_checks:
  - npm run verify:api
  - npm run test:migrations --workspace @vfbiz/api
  - npm run governance:check
revision: 5
review_date: "2026-07-23"
updated_at: "2026-07-23T09:11:44.314Z"
---

# Outcome

API Platform có bề mặt tài liệu runtime chuẩn NestJS: Swagger UI, Scalar API
Reference và OpenAPI JSON cùng sinh từ một document. Vehicle Catalog public
endpoints hiển thị response schema đủ rõ để developer, agent và SDK review
không phải suy đoán từ implementation.

## Constraints

- Không thay đổi public runtime behavior ngoài docs surface.
- Swagger sinh OpenAPI; Scalar chỉ render lại document, không tạo nguồn sự thật
  thứ hai.
- API docs mặc định chỉ bật ở development; staging/production phải bật rõ bằng
  environment variable.
- Dependency mới phải có runtime consumer thật và không đưa secret/API key vào
  config repository.

## Done when

- `@scalar/nestjs-api-reference` và dependency Fastify cần thiết được cài trong
  API workspace.
- Swagger UI phục vụ `/api-docs`, Scalar phục vụ `/reference`, OpenAPI JSON ở
  `/api-docs/openapi.json`.
- Vehicle Catalog DTO/response metadata xuất hiện trong exported OpenAPI.
- Contract smoke test kiểm runtime docs routes.
- API, migration và governance gates đạt.

## Checkpoint

- Code-complete: Swagger/Scalar docs surface, env toggle, Node engine alignment,
  Vehicle Catalog response DTO và runtime docs smoke test đã được triển khai.
  Exact next action: tiếp tục foundation bằng Public Account contract parity
  hoặc governed Source Revision/Vehicle Catalog release operations.

## Evidence

- [x] `npm run verify:api` — pass 2026-07-23; lint/typecheck/unit/e2e/Prisma/build pass.
- [x] `npm run test:migrations --workspace @vfbiz/api` — pass 2026-07-23; clean replay, drift, legacy backfill and PostgreSQL behavior pass.
- [x] `npm run governance:check` — pass 2026-07-23; docs/work/agent governance pass.
