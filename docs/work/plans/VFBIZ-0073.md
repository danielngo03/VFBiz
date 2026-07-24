---
id: VFBIZ-0073-plan
title: ExecPlan chuẩn hóa kiến trúc hai Next.js portal
status: active
owner_role: engineering-lead
scope: cross-system
when_to_read:
  - VFBIZ-0073
  - portal-architecture
  - provider-handoff
tags:
  - nextjs
  - customer-portal
  - workforce-portal
  - session-security
revision: 3
review_date: 2026-08-24
supersedes: []
---

# Purpose

Chuẩn hóa Customer Portal và Workforce Portal theo App Router feature-first,
loại loading/test scaffolding hình thức và gom session primitives dùng chung mà
không biến package chung thành authorization authority.

## Progress

- [x] Bảo toàn WIP bằng checkpoint.
- [x] Khôi phục governance gate và Customer typecheck.
- [x] Tích hợp Customer Portal lane.
- [x] Tích hợp Workforce Portal lane.
- [x] Tạo `@vfbiz/portal-session-core` và migrate shared HTTP/CSRF primitives.
- [x] Chuẩn hóa dependency, test scripts và artifact output.
- [ ] Hoàn tất authenticated Customer browser gate.

## Discoveries

- Customer có sáu `loading.tsx`; phần lớn chỉ khác nội dung text.
- Workforce Playwright artifact từng được commit do workspace `.gitignore` rỗng.
- Customer dùng `react-hook-form` qua hoisting thay vì dependency trực tiếp.
- Workforce khai báo dependency chưa có consumer và DAL chưa dùng generated SDK.
- Customer và Workforce token vault đã drift về OCC/logout/reconciliation.
- Workforce refresh trước đây có thể ghi sống lại session vừa logout; logout
  fence và conditional refresh write đã khắc phục race này.
- Customer vault monolith đã được tách bước đầu thành OIDC attempt store,
  coordination/replay store và Redis/encryption runtime; session repository và
  provider-revocation persistence vẫn được giữ cùng facade để bảo toàn API.
- `npm audit --omit=dev` còn advisory high ở Next/Nest/Prisma transitives;
  không dùng `--force` vì bản vá hiện yêu cầu version chưa ổn định hoặc breaking.

## Decision log

- Route files tiếp tục ngắn; skeleton và async data section thuộc feature.
- `app` chỉ routing/composition; `features` sở hữu nghiệp vụ; `platform` sở hữu
  hạ tầng kỹ thuật.
- Test source nằm trong `tests/`; generated output nằm dưới
  `local-data/test-artifacts/`.
- Shared session package chỉ chứa primitives, không chứa realm, audience, MFA,
  cookie hoặc business authorization policy.

## Delivery

1. Hai portal được refactor trên worktree độc lập.
2. Integration owner cherry-pick và giải quyết shared configuration.
3. Shared session package được đưa vào Customer trước, chạy parity tests, rồi
   mới migrate Workforce.
4. Root dependency/test scripts được cập nhật sau khi consumer đã tồn tại.

## Validation

- `npm run governance:check`
- `npm run contracts:lint`
- `npm run verify:apps`
- `npm run verify:apps:e2e`
- Security scan cho server/client boundary, token leakage, CSRF/origin và cache.

## Rollback

Checkpoint `8f4ba66` bảo toàn WIP trước refactor. Mỗi portal lane và shared
session migration có commit riêng để có thể revert độc lập.

## Outcomes

- Hai portal dùng chung feature-first convention và test taxonomy.
- Text-only loading đã bị loại; mỗi data panel có Suspense/skeleton theo layout.
- Generated artifacts nằm ngoài source tree.
- Workforce public Playwright đạt 2/2; Customer authenticated E2E đang chờ test
  identity, không được đánh dấu đạt giả.
