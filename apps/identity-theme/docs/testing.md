---
id: identity-theme-testing
title: Kiểm thử Identity Theme
status: active
owner_role: quality-lead
scope: identity-theme
when_to_read: Khi viết test hoặc chuẩn bị release Identity Theme.
tags: [identity, testing]
revision: 1
review_date: 2026-10-24
supersedes: []
---

# Kiểm thử Identity Theme

Gate tĩnh kiểm JAR layout, manifest, locale, hashed asset, external dependency
và template inventory. Gate runtime khởi động Keycloak 26.7.0, reconcile hai
realm rồi chạy browser flow thực.

Playwright phải bao phủ login, customer registration, reset, verify email,
required action, OTP/passkey/recovery và session expiry. Workforce phải không
có registration. Axe, keyboard và visual snapshot chạy trên VI/EN,
mobile/desktop, light/dark. Email HTML/text được nhận bởi SMTP sink; test không
ghi password, OTP, action token hoặc email thật vào artifact.
