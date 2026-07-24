---
id: adr-0004-dynamic-workforce-authorization
title: Dynamic Workforce Authorization
status: active
owner_role: architect
scope: root
when_to_read:
  - authorization
  - workforce-admin
  - workforce-portal
tags:
  - adr
  - authorization
  - workforce
revision: 1
review_date: 2026-10-24
supersedes: []
---

# ADR-0004: Dynamic Workforce Authorization

Date: 2026-07-24

## Context

Workforce release endpoints đang kiểm realm role cứng từ Keycloak. Cách này
không đáp ứng custom role, organizational scope, immediate revocation,
maker-checker hoặc object-level authorization của một workforce hub lớn.

## Decision

- API PostgreSQL sở hữu capability definition projection, role, assignment,
  organizational scope, approval state và entitlement revision.
- Keycloak sở hữu authentication, MFA, session và coarse workforce realm; JWT
  role không còn là business authorization authority sau cutover.
- Capability key do versioned repository contract định nghĩa. Quản trị viên chỉ
  ghép capability thành role và gán role trong scope được phép.
- Capability là action nguyên tử. Wildcard và universal super-admin bypass bị
  cấm.
- Privileged change dùng maker-checker: proposer và approver là hai verified
  subject khác nhau, có step-up MFA, reason, expiry và audit.
- Next.js Workforce Portal là BFF: browser chỉ giữ opaque HttpOnly session;
  token ở server-side vault. NestJS kiểm lại mọi protected action.
- Organizational scope chỉ dùng typed `global`, `market`, `showroom` hoặc
  `department`; không hỗ trợ user-authored policy DSL.

## Alternatives

- Keycloak canonical roles: không chọn vì business policy phụ thuộc provider và
  quyền trong access token có thể stale đến khi token hết hạn.
- Hybrid mirror capability vào token: không chọn ở baseline vì tạo hai nguồn
  trạng thái và tăng reconciliation risk.
- `read`/`manage` role đơn giản: không chọn vì không thể thể hiện submit,
  approve, activate, rollback và separation of duties.

## Consequences

- API cần entitlement decision service, revision-aware cache và additive
  authorization schema.
- Portal cần contract riêng, BFF session và secure server-only DAL.
- Current Keycloak roles được map sang system role trong shadow period; URL
  operations hiện có không cần đổi.
- Redis là optimization; database unavailable làm privileged authorization fail
  closed.

## Approval

Người dùng đã phê duyệt các quyết định kiến trúc trong yêu cầu triển khai ngày
2026-07-24. Production risk acceptance vẫn cần named Security, Architecture và
Release Owner.

