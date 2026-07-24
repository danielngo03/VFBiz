---
id: api-workforce-authorization
title: Workforce authorization
status: active
owner_role: engineering-lead
scope: api
when_to_read:
  - workforce-authorization
  - authorization
tags:
  - authorization
  - workforce-admin
  - identity
revision: 1
review_date: '2026-08-24'
supersedes: []
---

# Workforce authorization

## Boundary

Keycloak xác thực workforce identity, MFA và token audience. API PostgreSQL là
nguồn chuẩn duy nhất cho business capability, role, assignment và entitlement
revision. Realm role hoặc capability claim trong JWT không được dùng để quyết
định quyền nghiệp vụ.

Capability catalog được version bằng contract và migration. Quản trị viên được
ghép capability đã biết thành role; không được tạo permission string mới,
wildcard hoặc condition DSL.

## Decision flow

1. Authentication xác minh signature, issuer, audience, client và realm.
2. Capability guard đọc policy từ `@RequireCapabilities`.
3. `AuthorizationDecisionService` resolve active identity, role, assignment và
   scope từ PostgreSQL.
4. Assignment phải active, đã tới `effectiveAt`, chưa hết hạn và role chưa bị
   disabled.
5. Privileged capability yêu cầu MFA gần đây.
6. Application use case tiếp tục kiểm scope và object relationship khi resource
   chỉ biết tại runtime.
7. Thiếu identity, database evidence, capability hoặc scope đều fail closed.

Redis chỉ được dùng làm cache dẫn xuất trong phase sau. Cache key phải gồm
identity subject và entitlement revision; database vẫn là authority. Role hoặc
assignment mutation tăng revision và phát outbox event để invalidation.

## Role, assignment và scope

Role và assignment dùng optimistic concurrency, không hard-delete. Scope hợp
lệ:

- `global:global`
- `market:<external-ref>`
- `showroom:<external-ref>`
- `department:<external-ref>`

Scope khác global phải trỏ tới organization-unit projection active và đúng
type. Một capability ở scope rộng không được suy ra từ tên role.

System role do migration quản lý và không được disable từ API. Privileged role
change dùng change request có hạn dùng; người đề xuất không được tự approve
hoặc reject. Approval, mutation, audit, entitlement revision và outbox nằm
trong cùng transaction.

## HTTP contract

Workforce endpoints nằm trong `contracts/openapi/workforce-v1.yaml`, tách khỏi
customer SDK. Mutation yêu cầu `Idempotency-Key`, correlation ID và expected
version. Baseline hiện kiểm format idempotency key; durable replay ledger phải
được hoàn tất trước production cutover.

Public API và Workforce API không dùng chung một Scalar:

- `http://127.0.0.1:8000/reference/customer` là tài liệu Customer/Public API.
- `http://127.0.0.1:8000/reference/workforce` là tài liệu Workforce API nội bộ,
  read-only và chỉ được bật trong local/staging private ingress.
- `/reference` chỉ là exact redirect sang `/reference/customer`; không gắn
  Scalar middleware tại prefix cha để tránh bắt nhầm Workforce route.
- `VFBIZ_WORKFORCE_API_DOCS_ENABLED` mặc định bật ở development, tắt ở các môi
  trường khác và bị cấm bật ở production.
- Workforce contract YAML được phục vụ tại
  `/api-docs/workforce/openapi.yaml` với `private, no-store`.

Không tạo `/auth/workforce/login` trong NestJS. Workforce browser bắt đầu tại:

```text
GET http://localhost:3002/api/auth/login?returnTo=/authorization
```

Workforce Portal tạo state, nonce và PKCE verifier; chuyển browser tới Keycloak;
callback đổi authorization code ở server; token được mã hóa trong Redis token
vault; browser chỉ nhận opaque `HttpOnly` session cookie. Portal server dùng
short-lived access token để gọi `/api/v1/workforce/**`. Không dán refresh token,
client secret hoặc production token vào Scalar, browser storage hay log.

Bootstrap administrator không có public endpoint. Environment operator phải
provision đúng hai workforce identities đầu tiên bằng command kiểm soát ngoài
HTTP:

```bash
VFBIZ_AUTHORIZATION_BOOTSTRAP_ACK=CREATE_TWO_INITIAL_WORKFORCE_ADMINISTRATORS \
VFBIZ_BOOTSTRAP_WORKFORCE_ISSUER=https://identity.example.com/realms/vfbiz-workforce \
VFBIZ_BOOTSTRAP_ADMIN_SUBJECTS=<subject-a>,<subject-b> \
VFBIZ_BOOTSTRAP_ASSIGNMENT_EXPIRES_AT=<RFC-3339-within-24-hours> \
npm run authorization:bootstrap --workspace @vfbiz/api
```

Command không nhận password/token, không log OIDC subject, bắt buộc assignment
hết hạn trong tối đa 24 giờ, tạo audit/outbox trong cùng transaction và từ chối
chạy nếu hệ thống đang có đúng một global administrator. Khi đã có ít nhất hai
quản trị viên, command chỉ xác nhận và không ghi dữ liệu. Mọi recovery sau
bootstrap phải dùng runbook được phê duyệt, không chạy lại để vượt
maker-checker.

## Operational notes

- Không log token, raw identity attributes hoặc authorization payload nhạy cảm.
- Audit lưu actor reference, action, target, correlation và revision; không lưu
  access token.
- Quyền bị revoke làm request kế tiếp fail closed sau khi revision thay đổi.
- VFBIZ-0059 mới chịu trách nhiệm chuyển release endpoints cũ khỏi
  `@RequireRoles`; work item này không thay chúng.
