---
id: identity-theme-accessibility
title: Accessibility cho Identity
status: active
owner_role: design-lead
scope: identity-theme
when_to_read: Khi thay đổi layout, CSS, message hoặc interaction trong theme.
tags: [accessibility, identity]
revision: 1
review_date: 2026-10-24
supersedes: []
---

# Accessibility cho Identity

- Giữ semantic HTML, label, error association và focus behavior của Keycloak.
- Đạt WCAG 2.2 AA cho contrast, keyboard, focus visible và zoom 200%.
- Không dùng màu là tín hiệu duy nhất; error phải có text cụ thể.
- Hỗ trợ `prefers-reduced-motion`, system light/dark và viewport mobile.
- Không tự focus làm password manager hoặc browser back/refresh mất dữ liệu.
- Visual regression phải có VI/EN, mobile/desktop và light/dark.
