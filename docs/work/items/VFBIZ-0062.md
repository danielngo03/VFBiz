---
id: VFBIZ-0062
title: Hoàn thiện vòng đời session workforce và token rotation
status: active
mode: controlled
priority: P0
owner_team: workforce-experience
accountable_role: security-owner
primary_workspace: workforce-portal
affected_workspaces:
  - workforce-portal
  - infra
allowed_paths:
  - apps/workforce-portal
  - infra/local/keycloak
  - docs/work/items/VFBIZ-0062.md
  - WORK.md
depends_on:
  - VFBIZ-0057
controlled_signals:
  - authentication
  - authorization
  - workforce-admin
exclusive_resources:
  - workforce-session-contract
required_checks:
  - npm run verify:apps
  - npm run governance:check
revision: 3
review_date: "2026-08-24"
---

# Outcome

Workforce BFF duy trì session server-side an toàn qua access-token expiry,
refresh-token rotation và entitlement revision change mà không đưa token ra
browser.

## Constraints

- Refresh token chỉ tồn tại trong encrypted Redis token vault.
- Một session chỉ có một refresh operation tại một thời điểm.
- Refresh failure hoặc token reuse phải revoke local session và fail closed.
- Session lifetime, access-token lifetime và idle timeout là ba policy riêng.
- Không kéo dài session khi workforce identity, MFA hoặc entitlement đã bị revoke.

## Done when

- Access token được refresh trước expiry bằng rotation-safe single-flight.
- Concurrent request không tạo refresh-token reuse race.
- OIDC/session cookie được rotate sau login, MFA và entitlement material change.
- Absolute timeout, idle timeout, logout và provider revocation có negative tests.
- Token, client secret và raw OIDC claims không xuất hiện trong browser/log.

## Checkpoint

- Đã tách absolute BFF session lifetime khỏi access-token lifetime; callback
  bắt buộc verified email + MFA.
- Đã có rotation-safe refresh lease, subject session index, privacy-minimized
  device metadata, security status và logout-all route.
- Đã tách activity key khỏi encrypted token record, enforce idle timeout mà
  không tạo refresh write race; device listing không touch các phiên khác.
- Exact next action: cookie/session rotation sau entitlement revision và durable
  provider-outage reconciliation E2E.

## Evidence

- [x] Portal typecheck, 15 unit tests và production build đạt ngày 24/07/2026.
- [x] Hai Redis integration tests đạt: encrypted token material, subject-wide
  delete và idle expiry.
- [x] Governance check đạt ngày 24/07/2026.
- [ ] Entitlement-revision rotation và provider-outage browser E2E chưa hoàn tất.
