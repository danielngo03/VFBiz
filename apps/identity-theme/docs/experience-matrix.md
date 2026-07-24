---
id: identity-theme-experience-matrix
title: Ma trận luồng Identity
status: active
owner_role: product-owner
scope: identity-theme
when_to_read: Khi thêm hoặc thay đổi authentication flow.
tags: [identity, ux, keycloak]
revision: 1
review_date: 2026-10-24
supersedes: []
---

# Ma trận luồng Identity

| Luồng | Customer | Workforce |
|---|---:|---:|
| Login | Có | Có |
| Self-registration | Có | Không |
| Verify email | Có | Theo policy quản trị |
| Reset/update password | Có | Có |
| OTP, passkey, recovery code | Có | Có |
| SSO/Identity Provider | Khi được duyệt | Có |
| Consent/required action | Có | Có |
| Session expired/action token expired | Có | Có |

Tiêu đề và trợ giúp phải phản ánh đúng audience, nhưng security behavior và
error semantics vẫn do Keycloak sở hữu. Theme không được ẩn lỗi có thể hành
động, thêm credential field hoặc thay đổi authentication flow.
