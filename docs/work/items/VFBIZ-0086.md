---
id: VFBIZ-0086
title: Conversation content protection configuration
status: done
mode: controlled
priority: P0
owner_team: api-foundation
accountable_role: security-owner
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/.env.example
  - backend/api/src/platform/config
  - backend/api/src/platform/security
depends_on: []
controlled_signals:
  - pii
  - security
  - customer-conversation
exclusive_resources: []
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 7
review_date: "2026-08-25"
updated_at: "2026-07-24T17:33:33.892Z"
---

# Outcome

API Platform có typed keyring và authenticated-encryption primitive để
Conversation Runtime lưu nội dung inbox nhạy cảm dưới dạng ciphertext có key
revision, không ghi raw message vào PostgreSQL.

## Constraints

- Dùng Node.js `crypto` AES-256-GCM; không thêm dependency hoặc tự viết
  cryptographic construction mới.
- Keyring đến từ secret manager/environment; không commit key, plaintext hoặc
  generated local secret.
- Staging/production fail-fast khi active key/keyring thiếu hoặc sai.
- Ciphertext envelope pin version, key ID, nonce, authentication tag và AAD;
  decrypt không được fallback sang key khác khi key ID không khớp.
- Platform primitive không biết Conversation domain, customer hay database.

## Done when

- Environment schema parse một active key ID và JSON keyring gồm key 32-byte
  base64; từ chối duplicate/unknown/weak key và production config thiếu.
- Encrypt/decrypt dùng AES-256-GCM, random 96-bit nonce và caller-provided AAD.
- Tampered ciphertext/tag/AAD, unknown key ID và malformed envelope bị từ chối
  bằng typed error không lộ secret/plaintext.
- Rotation decrypt được envelope cũ bằng key ID và chỉ encrypt bằng active key.
- Unit tests không snapshot/log plaintext, key hoặc ciphertext production.

## Checkpoint

- Implemented a dedicated content-protection module with typed keyring parsing,
  AES-256-GCM envelopes, canonical versioned AAD, strict runtime decoding and
  bounded pre-authentication allocation.
- Independent security review found and verified fixes for authenticated key
  metadata, oversized nonce/tag allocation and module coupling.
- Exact next action: close this prerequisite, resume `VFBIZ-0018` and bind the
  persistence adapter to immutable owner/conversation/record/field context.

## Evidence

- [x] `npm run verify:api` — 44 unit suites / 220 tests, 9 E2E suites / 61
  tests, Prisma validation and Nest build passed on 25/07/2026.
- [x] `npm run governance:check` — docs, reports, authorization, 83 work items,
  instruction budgets, provider adapters, skills and 61 routing scenarios
  passed on 25/07/2026.
- [x] Security review — `agent_os_v7` confirmed no remaining P0/P1 blocker
  after the final envelope decoder and allocation-bound fixes.
