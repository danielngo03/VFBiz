---
id: VFBIZ-0013
title: Access principal và issuer policy foundation
status: done
mode: controlled
priority: P0
owner_team: api-foundation
accountable_role: security-owner
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/platform/security
  - backend/api/src/platform/config
  - backend/api/src/modules/access
  - backend/api/prisma/models/access.prisma
  - backend/api/prisma/migrations
  - backend/api/test
  - backend/api/.env.example
  - backend/api/docs
  - docs/work
  - WORK.md
depends_on:
  - VFBIZ-0012
controlled_signals:
  - authentication
  - authorization
  - schema
  - migration
exclusive_resources:
  - database-migration
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 5
review_date: "2026-08-23"
updated_at: "2026-07-23T05:42:17.576Z"
---

# Outcome

Resource API xác thực access token từ đúng hai trust profile `customer` và
`workforce`, tạo `AccessPrincipal` có realm rõ ràng và từ chối mọi issuer,
audience hoặc authorized party ngoài allowlist trước khi domain code chạy.

## Constraints

- Browser dùng same-origin BFF; token chỉ tồn tại phía server. Resource API chỉ
  nhận Bearer access token từ BFF hoặc mobile client được phê duyệt.
- Untrusted `iss` chỉ được dùng để chọn một trust profile đã cấu hình; tuyệt đối
  không được tạo URL discovery/JWKS từ issuer do request cung cấp.
- Customer và workforce phải có issuer, audience, JWKS URI, client allowlist và
  session namespace độc lập.
- Không provision Customer Profile từ workforce principal.
- HTTP issuer/JWKS chỉ được chấp nhận ở `development` hoặc `test`.

## Done when

- Environment contract không còn một cặp OIDC dùng chung cho hai realm.
- `AccessPrincipal` phân biệt `customer`/`workforce`, giữ `sub`, `iss`, `aud`,
  `azp`, `sid`, `acr`, `amr` và scope đã được xác minh.
- Wrong issuer, audience, authorized party, algorithm, expired token và token
  thiếu claim bắt buộc đều bị từ chối theo cùng Problem Details contract.
- Customer-only guard từ chối workforce principal dù token hợp lệ.
- Unit/E2E negative authorization tests và API quality gate đạt.

## Checkpoint

- Customer/workforce trust profile, principal realm và realm guard đã được
  triển khai; exact next action là đóng work item và mở VFBIZ-0014.

## Evidence

- [x] `npm run verify:api` — lint/typecheck, 42 unit/architecture tests,
  12 E2E tests, Prisma validation và Nest build đạt ngày 2026-07-23.
- [x] `npm run governance:check` — 49 durable docs, 13 work item và
  37 provider-neutral routing scenario đạt ngày 2026-07-23.

Residual gate: same-origin BFF session/callback/revoke là capability của Portal
và Access session lifecycle sau foundation này; resource API hiện đã fail-closed
cho issuer/audience/client không thuộc allowlist.
