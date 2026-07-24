---
id: VFBIZ-0074
title: Enterprise Keycloak identity experience
status: review
mode: controlled
priority: P0
owner_team: identity-experience
accountable_role: identity-platform-owner
primary_workspace: identity-theme
affected_workspaces:
  - root
  - infra
  - identity-theme
  - design-tokens
  - customer-portal
  - workforce-portal
allowed_paths:
  - apps/identity-theme
  - packages/design-tokens
  - infra/keycloak
  - infra/local/keycloak
  - apps/customer-portal
  - apps/workforce-portal
  - .agents/organization.json
  - tools/lib/governance.mjs
  - tests/governance/scenarios.json
  - docs/decisions
  - docs/architecture
  - docs/governance
  - docs/work/items/VFBIZ-0074.md
  - docs/work/plans/VFBIZ-0074.md
  - package.json
  - package-lock.json
  - .dockerignore
  - .gitignore
  - WORK.md
depends_on: []
controlled_signals:
  - authentication
  - identity-theme
  - dependency-policy
  - brand-rights
exclusive_resources:
  - dependency-lockfile
  - agent-organization-registry
required_checks:
  - npm run verify:governance
  - npm run verify:identity-theme
  - npm run verify:design-tokens
  - infra/local/keycloak/native-check.sh
  - npm run test:e2e --workspace @vfbiz/identity-theme
revision: 6
review_date: "2026-08-24"
updated_at: "2026-07-24T10:26:51.260Z"
---

# Outcome

Customer và Workforce authentication flows được Keycloak 26.7.0 render bằng
hai theme variant dùng chung design-token contract, có artifact JAR xác minh
được và local realm reconcile không drift.

## Constraints

- Không đưa password, OTP, recovery code hoặc WebAuthn response vào Next.js.
- Không dùng remote asset, font, analytics, script hoặc VinFast brand asset
  chưa được Brand/Legal phê duyệt.
- Account/Admin Console không nằm trong baseline.
- Theme phải được cài trước khi reconciler gán vào realm đang tồn tại.

## Done when

- JAR chứa đúng `META-INF/keycloak-themes.json` và ba theme dưới `theme/`.
- Customer và Workforce có VI/EN, login/email theme riêng và registration
  policy đúng.
- Design tokens được sinh deterministic và có ba consumer thật.
- Local native/Compose cài artifact trước khi Keycloak start/reconcile.
- Governance, design-token, theme contract và live Keycloak checks đạt.

## Checkpoint

- Design tokens, native theme JAR, immutable image recipe, live realm reconcile,
  WebAuthn/Recovery provider policy và browser smoke/accessibility gate đã đạt.
- Exact next action: bổ sung SMTP sink và credential-backed OTP/passkey/
  recovery visual regression trước production release.

## Evidence

- [x] `npm run verify:governance` — 61 provider-neutral scenarios đạt.
- [x] `npm run verify:identity-theme` — JAR, manifest, hashed asset và template
  inventory đạt; SHA-256 `be6b8f31ffb85a7bc4817b900b3eee408840af7b9cc2cae971b62d59eb4cd4f6`.
  Hai build liên tiếp tạo cùng checksum.
- [x] `npm run verify:design-tokens` — generated contract và self-contained
  asset tests đạt.
- [x] `infra/local/keycloak/native-check.sh` — hai realm, theme, locale,
  registration, WebAuthn, recovery provider và OIDC policy đạt trên 26.7.0.
- [x] `npm run test:e2e --workspace @vfbiz/identity-theme` — Customer
  registration/reset, Workforce no-registration, VI/EN, dark/mobile và
  Axe/WCAG smoke: 5/5 đạt.

### active — 2026-07-24T10:19:20.497Z

Local baseline complete; production release still requires SMTP sink and credential-backed OTP/passkey/recovery visual evidence.

### review — 2026-07-24T10:26:51.260Z

Implementation and local runtime evidence complete; awaiting Identity, Design, Security and Brand/Legal review before production release.
