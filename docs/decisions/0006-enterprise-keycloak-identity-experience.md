---
id: ADR-0006
title: Keycloak sở hữu Identity Experience
status: active
owner_role: architect
scope: cross-system
when_to_read:
  - identity-theme
  - authentication
  - keycloak
tags: [architecture, identity, keycloak, design-system]
revision: 1
review_date: 2026-10-24
supersedes: []
context_anchors:
  identity-theme: "## Decision"
  authentication: "## Security boundary"
---

# ADR 0006: Keycloak sở hữu Identity Experience

## Context

Customer và Workforce cần trải nghiệm đăng nhập nhất quán nhưng có audience,
registration policy và risk profile khác nhau. Việc render credential form
trong Next.js sẽ khiến portal nhận password, OTP hoặc WebAuthn response và mở
rộng trust boundary không cần thiết.

## Decision

- Giữ hai realm `vfbiz-customer` và `vfbiz-workforce`.
- Keycloak trực tiếp render login, registration, recovery, MFA, passkey và
  required action.
- Một native theme JAR chứa abstract `vfbiz-foundation` cùng hai selectable
  theme `vfbiz-customer` và `vfbiz-workforce`.
- Source UI nằm tại `apps/identity-theme`; `infra` chỉ đóng gói, cài đặt,
  reconcile và health-check artifact.
- `packages/design-tokens` là contract build-time cho Customer Portal,
  Workforce Portal và Identity Theme. Không chia sẻ React component.
- Chỉ tùy biến CSS, messages và resource cần thiết. Không copy upstream
  FreeMarker template khi inheritance đã đáp ứng.
- Chưa dùng asset/logo/font VinFast cho tới khi Brand/Legal phê duyệt.

## Security boundary

Portals chỉ khởi tạo Authorization Code + PKCE và nhận callback qua BFF.
Password, OTP, recovery code, action token và WebAuthn response không đi qua
portal. Theme không thêm analytics, CDN, third-party script hoặc remote font.

## Consequences

Theme trở thành deployable artifact có version, checksum và compatibility gate
với Keycloak. Nâng Keycloak bắt buộc chạy lại visual, accessibility và
authentication-flow regression. Production rollback dùng image/JAR version
trước thay vì sửa container trực tiếp.
