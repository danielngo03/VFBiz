---
id: identity-theme-architecture
title: Kiến trúc Identity Experience
status: active
owner_role: identity-platform-owner
scope: identity-theme
when_to_read: Khi thay đổi Keycloak theme, login/email experience hoặc design token.
tags: [identity, keycloak, theme]
revision: 1
review_date: 2026-10-24
supersedes: []
context_anchors:
  - signal: identity-theme
    heading: Ranh giới
---

# Kiến trúc Identity Experience

## Ranh giới

Keycloak trực tiếp render và xử lý password, OTP, recovery code, passkey và
required action. Customer Portal và Workforce Portal chỉ khởi tạo OIDC flow;
không proxy hoặc thu thập credential.

`vfbiz-foundation` chứa ngôn ngữ thiết kế chung nhưng là abstract theme.
`vfbiz-customer` và `vfbiz-workforce` là hai theme selectable, tương ứng hai
realm cô lập. Chúng chỉ kế thừa CSS, messages và resource đã kiểm soát; không
chia sẻ React component với portal.

## Artifact

Build tạo một JAR versioned với đúng classpath `META-INF/keycloak-themes.json`
và `theme/...`. Design tokens được đưa vào tại build time dưới tên có content
hash. Production image copy JAR vào `/opt/keycloak/providers` và chạy
`kc.sh build`.

## Dependency rule

Identity Theme phụ thuộc một chiều vào generated design tokens. `infra/keycloak`
chỉ đóng gói artifact; `infra/local/keycloak` chỉ cài đặt, reconcile và kiểm tra
realm. Không workspace hạ tầng nào sở hữu source UI.
