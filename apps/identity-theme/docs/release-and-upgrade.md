---
id: identity-theme-release-upgrade
title: Phát hành và nâng cấp Identity Theme
status: active
owner_role: identity-platform-owner
scope: identity-theme
when_to_read: Khi build image, release, rollback hoặc nâng Keycloak.
tags: [identity, release, keycloak]
revision: 1
review_date: 2026-10-24
supersedes: []
---

# Phát hành và nâng cấp Identity Theme

## Release

1. Build design tokens và theme JAR từ clean revision.
2. Xác minh archive layout, checksum, SBOM và test flow.
3. Build Keycloak image từ digest-pinned base image, copy JAR rồi chạy
   `kc.sh build`.
4. Phát hành canary/blue-green; theo dõi login failure và required-action error.
5. Rollback bằng image digest trước, không sửa trực tiếp container.

## Upgrade

Chạy compatibility suite trên phiên bản Keycloak hiện tại và ứng viên kế tiếp.
Mọi FreeMarker override mới phải có lý do, owner và regression test vì upstream
template có thể thay đổi. Không merge upgrade khi login, registration, reset,
MFA, passkey, recovery hoặc email flow chưa đạt.
