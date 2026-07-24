---
id: workforce-portal-testing
title: Kiểm thử Workforce Portal
status: active
owner_role: engineering-lead
scope: workforce-portal
when_to_read:
  - workforce-testing
context_anchors:
  workforce-testing: "## Taxonomy"
tags:
  - testing
  - nextjs
revision: 1
review_date: 2026-08-24
supersedes: []
---

# Kiểm thử Workforce Portal

## Taxonomy

- `tests/unit`: presentation model và pure policy.
- `tests/component`: accessible UI trong jsdom.
- `tests/integration`: route/session/token-vault.
- `tests/e2e`: hành vi browser qua Playwright.
- `tests/support`: setup và test-only shims.

Generated traces, screenshots và HTML report nằm trong
`local-data/test-artifacts/workforce-portal`; không nằm trong source tree hoặc
Git.

## Lệnh

```bash
npm test --workspace @vfbiz/workforce-portal
npm run test:integration --workspace @vfbiz/workforce-portal
npm run test:e2e --workspace @vfbiz/workforce-portal
```

Route thay đổi phải có browser evidence. Auth/session change là controlled và
phải chạy integration test trước E2E. Test không được log token, cookie, raw IP
hoặc payload authorization nhạy cảm.
