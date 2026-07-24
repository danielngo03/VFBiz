---
id: VFBIZ-0074-plan
title: ExecPlan Keycloak Identity Experience
status: active
owner_role: identity-platform-owner
scope: cross-system
when_to_read:
  - VFBIZ-0074
  - identity-theme
context_anchors:
  VFBIZ-0074: "## Progress"
  identity-theme: "## Decisions"
tags:
  - keycloak
  - identity
  - design-system
revision: 1
review_date: 2026-08-24
supersedes: []
---

# Purpose

Tạo identity experience do Keycloak render cho Customer và Workforce mà không
di chuyển credential handling sang portal.

## Progress

- [x] Audit realm, deployment và brand governance hiện tại.
- [x] Build design-token contract.
- [x] Build native login/email theme JAR.
- [x] Wire local install, reconcile và verification.
- [x] Add deterministic, accessibility và browser smoke evidence.
- [ ] Add SMTP sink and credential-backed OTP/passkey/recovery visual suite
  before production release.

## Decisions

- `apps/identity-theme` sở hữu deployable UI artifact.
- `packages/design-tokens` là nguồn token build-time duy nhất.
- `infra` chỉ cài và vận hành artifact; không sở hữu template/CSS.
- Một JAR chứa abstract foundation cùng Customer/Workforce variants.
- Ưu tiên inheritance, CSS và messages; không copy upstream template inventory.

## Validation

- `npm run verify:design-tokens`
- `npm run verify:identity-theme`
- `npm run verify:governance`
- `infra/local/keycloak/native-check.sh`

## Rollback

Giữ theme mặc định cho tới khi artifact và reconcile checks đạt. Rollback bằng
JAR/image version trước và realm theme selection trước.
