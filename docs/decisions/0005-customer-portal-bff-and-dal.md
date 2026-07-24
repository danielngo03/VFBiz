---
id: adr-0005-customer-portal-bff-and-dal
title: ADR 0005 — Customer Portal BFF và server DAL
status: active
owner_role: architect
scope: cross-system
when_to_read:
  - customer-portal
  - customer-bff
  - customer-auth
  - customer-session
  - customer-journey
tags:
  - adr
  - nextjs
  - oidc
  - customer
revision: 1
review_date: 2026-08-24
supersedes: []
---

# ADR 0005 — Customer Portal BFF và server DAL

## Status

Accepted cho Customer Portal foundation. Security/Privacy Owner vẫn phải duyệt
evidence auth, session, consent và DSAR trước release.

## Context

Customer Portal cần phục vụ các journey đã xác thực mà không phát access token
cho browser. Portal đồng thời phải dùng đúng authority của NestJS, tránh gọi
ngược qua public Route Handler khi render trên server và tránh biến Next.js
layout/middleware thành authorization boundary.

## Decision

1. Customer Portal dùng Next.js 16 App Router và React Server Components mặc
   định. Client Component chỉ dùng khi cần browser state hoặc interaction.
2. Next.js là BFF cho OIDC Authorization Code + PKCE. Browser chỉ giữ opaque
   session cookie; encrypted access/refresh token nằm trong server-side Redis
   token vault.
3. Server-only DAL gọi NestJS resource API trực tiếp khi render. Server Action
   xử lý form mutation; Route Handler chỉ dành cho browser-specific auth/BFF
   operation hoặc endpoint cần callback.
4. `proxy.ts` chỉ hỗ trợ optimistic redirect. DAL và NestJS đều kiểm session;
   NestJS là business authorization và object-authorization authority.
5. Public resource contract `public-v1` mô tả `/api/v1`. Browser contract
   `customer-bff-v1` mô tả `/api/auth` và `/bff`; hai contract không dùng chung
   security scheme mơ hồ.
6. Portal dùng generated API types. Browser không gọi NestJS bằng bearer token
   và token không nằm trong `localStorage`, `sessionStorage`, HTML, client
   bundle hoặc log.
7. Protected response là `private, no-store`. Mutation kiểm origin/CSRF phù hợp,
   runtime schema, optimistic version và provider reconciliation.
8. Account, security/session, privacy/DSAR và self-reported Garage là current
   scope. Catalog chỉ phục vụ model/variant selector.
9. Journey/design-system change cần experience/accessibility evidence; auth,
   session và PII change cần focused risk review.

## Consequences

- Portal có thêm server DAL, feature boundaries và browser acceptance tests.
- Auth/BFF contract có thể tiến hóa độc lập với NestJS resource contract.
- Redis outage làm session fail closed; PostgreSQL không được dùng làm token
  fallback.
- Direct server DAL giảm hop nhưng mọi mutation vẫn phải giữ correlation,
  idempotency, ETag và error mapping.

## Rejected alternatives

- SPA giữ bearer/refresh token: tăng token exposure và phá BFF boundary.
- Server Component gọi vòng qua `/bff`: thêm network hop và làm mờ ownership.
- Chỉ kiểm quyền trong layout/proxy: không bảo vệ Server Action, Route Handler
  hoặc direct API request.
- Một OpenAPI cho cả CIAM redirect và business resource: trộn host, caller và
  security semantics.
- Tạo shared design-system package ngay: chưa có consumer thứ hai đã được duyệt.

## Verification

- Login/callback/refresh/logout/back-channel logout có browser evidence.
- Profile stale ETag, session revoke/logout-all, consent, DSAR và Garage chạy
  E2E với failure states.
- Không token exposure hoặc browser bearer request tới NestJS.
- Typecheck, lint, unit/component, Redis integration, axe và production build
  đạt; cross-subject denial tiếp tục được NestJS kiểm chứng.
