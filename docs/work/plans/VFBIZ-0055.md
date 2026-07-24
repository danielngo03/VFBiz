---
id: plan-VFBIZ-0055
title: ExecPlan Workforce Portal và Dynamic Authorization
status: active
owner_role: engineering-lead
scope: cross-system
when_to_read:
  - VFBIZ-0055
  - VFBIZ-0056
  - VFBIZ-0057
  - VFBIZ-0058
  - VFBIZ-0059
  - VFBIZ-0060
tags:
  - workforce
  - authorization
  - nextjs
revision: 3
review_date: 2026-08-24
supersedes: []
---

# Purpose

Đổi Operations Admin thành Workforce Portal và thay hard-coded workforce roles
bằng capability-based authorization do API sở hữu.

## Progress

- [x] VFBIZ-0055: ADR và capability contract.
- [ ] VFBIZ-0056: authorization schema, decision service và workforce API
  (runtime đã có; còn durable idempotency và invalidation transport).
- [x] VFBIZ-0057: rename workspace, Next.js BFF và design foundation.
- [ ] VFBIZ-0058: role, assignment, approval và audit UX.
- [ ] VFBIZ-0059: migrate release endpoints sang capability.
- [ ] VFBIZ-0060: security/E2E/shadow cutover evidence.

## Decisions

- API PostgreSQL là nguồn chuẩn cho business authorization.
- Keycloak chỉ xác thực workforce identity/MFA.
- Next.js giữ opaque browser session; token nằm server-side.
- Capability là action nguyên tử; assignment có typed organization scope.
- Privileged change dùng maker-checker với hai subject khác nhau.
- Bootstrap hai quản trị viên đầu tiên chỉ chạy bằng command ngoài HTTP, yêu
  cầu explicit acknowledgement và từ chối partial-authority state.
- Active workspace là `apps/workforce-portal`, thuộc team
  `workforce-experience` và phòng ban `Workforce Applications`.

## Delivery lanes

- Lane A: API Access context, Prisma migration và workforce contract.
- Lane B: Workforce Portal Next.js, BFF và authorization UX.
- Lane C: repository governance, docs, provider routing và verification.

Migration, lockfile, workforce contract và organization registry chỉ có một
writer tại một thời điểm.

## Validation and recovery

- Shadow-compare role decision cũ và capability decision mới trước cutover.
- Database migration là additive; rollback là tắt enforcement V2, không xóa
  authorization records.
- Portal không trở thành enforcement authority.
- Không merge, deploy hoặc tuyên bố production approval từ agent evidence.
- Dependency audit ngày 24/07/2026 còn 7 high advisory từ dependency transitive
  của NestJS/Fastify, Prisma và Next.js. Không dùng `npm audit fix --force`;
  Security Owner phải theo dõi bản vá upstream hoặc chấp nhận exception có hạn.
