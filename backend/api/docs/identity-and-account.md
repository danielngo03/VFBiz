---
id: api-identity-and-account
title: Identity và Account runtime
status: active
owner_role: engineering-lead
scope: api
when_to_read:
  - identity
  - customer-account
  - customer-profile
  - consent
  - customer-session
  - dsar
tags:
  - nestjs
  - identity
  - customer
  - privacy
revision: 12
review_date: 2026-08-23
supersedes: []
---

# Identity và Account runtime

## Boundary

“Account” là customer journey, không phải một module gom mọi thứ:

- CIAM/Keycloak sở hữu registration, password, email verification, recovery,
  MFA, authentication flow và identity session.
- Customer Portal sở hữu toàn bộ browser OIDC flow tại `/api/auth/**`, kiểm
  state/return URL, giữ token trong server-side vault và không bao giờ nhận
  password.
- NestJS không còn expose `/auth/customer/**` hoặc nhận access token từ cookie.
  Security platform chỉ nhận Bearer token, xác minh principal rồi materialize
  `IdentitySubject` và `SessionProjection` từ verified temporal claims cùng
  `sid`; Customer persistence adapter provision profile khi customer dùng
  `/me`.
- `customer` sở hữu Customer Profile, consent ledger, DSAR và garage preference.
- Customer Portal BFF tại port 3001 sở hữu browser OIDC callback, opaque
  `HttpOnly` session cookie và encrypted Redis token vault; mobile
  tương lai dùng Authorization Code + PKCE. Cả hai gọi API bằng identity đã được
  API xác minh; client không tự truyền subject có thẩm quyền.

API không dùng Keycloak-specific class trong domain/application. CIAM nằm sau
port để có thể thay provider mà không đổi Customer aggregate.

## Principal và subject provisioning

`AccessPrincipal` gồm issuer, subject, audience, authorized party, scopes,
verified realm roles, session ID, authentication context/methods và derived
realm từ allowlisted issuer policy. `email_verified` chỉ được dùng sau khi
signature/issuer/audience đã verify; `amr` chỉ chứng minh MFA của phiên hiện
tại, không tự chứng minh người dùng vẫn còn credential MFA. Role chỉ được đọc từ access token đã verify;
unsigned header hoặc request body không bao giờ có thẩm quyền. Kết quả trực tiếp
từ verifier có thêm `iat`, `exp` và
`auth_time` đã xác minh để materialize session; thiếu `sid` làm callback fail
closed. Không tin realm, role, email hoặc customer ID trong unsigned header.

Resource API có đúng hai trust profile cấu hình riêng:

- `customer`: customer issuer/audience/JWKS URI và BFF/mobile client allowlist;
- `workforce`: workforce issuer/audience/JWKS URI và workforce BFF allowlist.

Customer BFF callback chỉ hoàn tất khi access token đã verify, đúng customer
realm/client, có `sid` và `email_verified=true`. MFA của customer hiện là tùy
chọn theo chính sách tài khoản; `/api/auth/configure-mfa` chỉ khởi tạo
Keycloak `CONFIGURE_TOTP` action và VFBiz không nhận OTP secret. Workforce
Portal bắt buộc verified email và OTP/WebAuthn trước khi tạo BFF session.

Customer browser auth được cấu hình tại Customer Portal, không phải API:

- `CUSTOMER_OIDC_CLIENT_ID`
- `CUSTOMER_OIDC_REDIRECT_URI`
- `CUSTOMER_SESSION_COOKIE_NAME`
- `CUSTOMER_SESSION_COOKIE_SECURE`
- `CUSTOMER_TOKEN_VAULT_KEY`
- `CUSTOMER_REDIS_URL`

Trong development, cookie name không dùng prefix `__Host-` nếu chạy HTTP
localhost. Production bắt buộc HTTPS và secure cookie. Customer Portal mutation
dùng cookie phải kiểm exact Origin và synchronizer CSRF token lấy từ encrypted
session. Token không được trả về browser.

Customer Portal đã có opaque session ID, AES-256-GCM Redis token vault,
single-flight refresh, idle/absolute timeout và signed OIDC back-channel logout
theo provider `sid`. NestJS token-cookie flow đã được loại khỏi composition
root; `public-v1` chỉ mô tả Bearer resource API và `customer-bff-v1` mô tả
browser session/auth surface.

Verifier chỉ dùng claim `iss` chưa xác minh để tra exact issuer trong allowlist.
JWKS URI luôn lấy từ cấu hình tin cậy, không ghép từ input. Sau đó mới verify
signature, algorithm, `typ`, issuer, audience, expiry, `sub` và `azp`.
Production chỉ chấp nhận HTTPS. ID token không được dùng làm resource access
token.

Provisioning lần đầu:

1. Verify signature, algorithm allowlist, issuer, audience, expiry và subject.
2. Map `(issuer, subject)` thành một `IdentitySubject` trong transaction.
3. Chỉ customer issuer/profile mới được tạo `CustomerProfile`.
4. Unique constraint và retry hữu hạn xử lý concurrent first request.
5. Disabled subject/profile bị từ chối; không tự kích hoạt lại từ token cũ.

`@RequireIdentityRealm('customer')` hoặc `workforce` là policy ở presentation
boundary; nó không thay object-level authorization trong application service.

Workforce operation dùng capability từ PostgreSQL, organizational scope,
object policy và authentication assurance. Keycloak role chỉ còn phục vụ
migration/shadow comparison, không phải business authority. Local Keycloak
realm dùng `oidc-amr-mapper`; thiếu `otp`/`webauthn` hoặc email chưa verify làm
Workforce BFF callback fail closed.

Không lưu full claims. Email/phone chỉ được projection khi có business purpose,
classification, encryption/tokenization và freshness policy riêng.

## Aggregate và lifecycle

### Identity Subject

| Field | Ý nghĩa |
| --- | --- |
| `id` | UUID nội bộ, không suy đoán được |
| `issuer`, `subject` | Opaque external identity key, unique cùng nhau |
| `realm` | `customer` hoặc `workforce` từ issuer policy |
| `status` | `active`, `suspended`, `deleted` |
| timestamps | Provision/update time, không thay IdP authentication event |

### Customer Profile

- `id`, `identitySubjectId`, `displayName`.
- `locale`, IANA `timezone`, `market`.
- Typed communication preferences; default đầy đủ `email=false`,
  `sms=false`, `push=false`.
- `status`, optimistic `version`, timestamps.

Profile update cần `If-Match`/expected version. Stale update không overwrite;
trả Problem Details `PROFILE_VERSION_CONFLICT`.

Runtime hiện có `GET/PATCH /api/v1/me`; GET provision identity/profile
idempotently cho customer principal hợp lệ, PATCH dùng ETag `"profile-N"`.
PATCH tái kiểm tra identity/profile active trong cùng serializable transaction
với state update, redacted audit và `customer.profile.updated.v1` outbox; một
token cũ không thể ghi tiếp sau khi subject bị suspend.

### Consent ledger

Consent là event append-only:

- purpose allowlist;
- policy version;
- `granted` hoặc `withdrawn`;
- capture source, evidence reference, correlation ID và occurred time.

Current consent được suy từ event mới nhất theo deterministic order. Không
`UPDATE`/`DELETE` event qua customer API; correction là event mới có reason và
audit. Consent không đồng nghĩa communication preference.

`PUT /api/v1/me/consents` bắt buộc `Idempotency-Key`; source được suy từ
authorized client, không lấy từ body. Cùng key/cùng payload trả current state,
cùng key/khác payload bị từ chối.

`policyVersion` do client gửi chỉ là reference, không phải authority. Persistence
chỉ chấp nhận version tồn tại trong `ConsentPolicy`, đúng purpose, state
`active`, nằm trong effective window và có checksum + approval evidence. Consent
event, redacted audit và `customer.consent.changed.v1` outbox commit atomically;
downstream consumer phải fail closed khi chưa xử lý withdrawal.

### Session projection và identity assurance

Keycloak là nguồn chuẩn cho password, credential, email verification, MFA
enrollment và provider session. PostgreSQL không sao chép password, OTP seed,
recovery code hoặc raw provider token.

API chỉ lưu projection cần cho local denial, UX và audit:

- hash của BFF/provider session reference;
- device label và sanitized user-agent summary;
- IP ở dạng network prefix (`/24` hoặc `/64`), không lưu raw IP;
- email-verification và MFA evidence quan sát được tại phiên;
- authentication/last-seen/expiry/revoke time và reconciliation state.

`deviceLabel`, user-agent và network prefix chỉ là observation hỗ trợ người dùng
nhận biết phiên, không phải device identity và không được dùng một mình để
authorize. VFBiz chưa tạo fingerprint bền vững hoặc “trusted device” vì chưa có
risk-engine consumer, consent/retention policy và false-positive handling.

`GET /api/v1/me/sessions/security` trả email verification, MFA enrollment từ
protected Keycloak Admin bridge và MFA evidence của current session. Nếu bridge
không cấu hình/không sẵn sàng, provider-backed field trả `null`, không suy đoán.
`DELETE /api/v1/me/sessions` deny tất cả local sessions trước rồi yêu cầu
subject-wide logout ở Keycloak; response nói rõ `confirmed`,
`retry_required` hoặc `manual_review_required`.

Callback đầu tiên atomically upsert identity và session; refresh chỉ cập nhật
observation có revision mới hơn. Concurrent callback dùng transaction
`SERIALIZABLE` với retry hữu hạn. Logout đánh dấu current local projection bị
revoke trước khi xóa cookie, kể cả CIAM đang unavailable.

Revoke flow gọi CIAM adapter ngoài database transaction, lưu pending outcome và
reconcile khi provider timeout. Current session không được xác định bằng
session ID do client tự khai.

Keycloak Admin bridge dùng service account riêng, client-credentials và tối
thiểu `view-users`/`manage-users`; secret chỉ đến từ secret manager/env runtime.
Nếu bridge không cấu hình, local deny vẫn có hiệu lực nhưng provider
reconciliation không được báo giả là thành công.

Redis token vault không phải business database hoặc audit authority. Production
phải tách auth session plane khỏi cache plane, dùng `noeviction`, TLS, service
ACL, network isolation, capacity alert và HA theo RTO/RPO được duyệt. Cache
vehicle/location có TTL/eviction riêng; không dùng chung token-vault namespace.
Nếu token vault mất record, BFF trả `401` và yêu cầu đăng nhập lại vì refresh
token cũng đã mất; không được tuyên bố có thể tự refresh từ dữ liệu không còn.

### Customer Data Request

`export` và `delete` là idempotent workflow có state:

```text
requested -> processing -> completed
                    \-> partially_completed -> retry
requested|processing -> rejected
```

Khi nhận request, API atomically snapshot target registry theo version, ghi
event khởi tạo, audit metadata đã redact và outbox event. Target state tách
`pending`, `processing`, `completed`, `retry_required`, `legally_retained` và
`permanent_failure`; retry/lease/fencing thuộc worker, không thuộc customer API.

Job fan-out tới API, CIAM, AI, object storage và telemetry owner qua adapter.
Artifact export nằm ở private object storage, short-lived và access-controlled;
database chỉ giữ object reference. Legal hold phải có authority/evidence.

`POST /api/v1/me/data-requests` tạo request `requested` idempotently.
`GET /api/v1/me/data-requests` và `GET /api/v1/me/data-requests/{id}` chỉ trả
customer-visible lifecycle state theo verified subject; không expose target,
provider error hoặc evidence nội bộ. Worker fan-out, artifact generation,
hard-delete, retention/legal-hold policy và secure download vẫn là work item
controlled riêng; foundation không được mô tả là DSAR execution hoàn chỉnh.

## Authorization

- `/me` luôn derive customer từ verified principal.
- Không có endpoint nhận `customerProfileId` trong body để truy cập own data.
- Same `subject` từ issuer khác là identity khác.
- Customer token không gọi workforce route và ngược lại.
- Scope là điều kiện cần, object relationship mới là điều kiện đủ.
- Mọi sensitive denial có generic external shape và redacted security telemetry.

## Idempotency, audit và transaction

- Namespace idempotency bind operation + actor + target.
- Cùng key/cùng request trả outcome cũ; cùng key/khác request bị từ chối.
- Mutation, idempotency record, allowlisted audit metadata và outbox commit
  atomically khi không có provider call.
- Profile và Garage audit chỉ ghi changed-field names, stable record IDs,
  version và invariant state; nickname/profile values không đi vào event.
- Garage create/update/archive phát versioned outbox event trong cùng
  serializable transaction. Create replay trả outcome cũ và không phát event
  lần hai.
- Audit không chứa profile snapshot, token, cookie, raw contact, VIN hoặc DSAR
  payload.
- Provider call dùng intent/outbox/reconciliation; không giữ transaction trong
  lúc gọi CIAM.

## Retention và deletion

Retention không được hard-code nếu chưa có Privacy/Legal/Data Owner approval.
Mỗi record cần policy ID và deletion behavior:

- Profile/identity: tombstone hoặc delete mapping theo legal basis.
- Session: purge sau expiry + security window được duyệt.
- Consent: giữ evidence theo legal obligation nhưng pseudonymize subject khi
  lawful.
- DSAR artifact: TTL ngắn; completion record không sao chép exported PII.
- Idempotency/outbox/audit: allowlist payload và purge theo purpose.

Append-only không đồng nghĩa giữ vĩnh viễn.

## Required tests

- Cross-issuer same-subject, wrong audience/realm, disabled subject/profile.
- Concurrent first-request provisioning không tạo duplicate.
- Profile ETag/If-Match, stale version và lost-update.
- Consent append-only/current-state ordering.
- Session revoke ownership, provider timeout và reconciliation.
- DSAR replay, partial failure, legal hold và deletion lineage.
- Logs/audit/outbox/idempotency không chứa token, email, phone hoặc raw PII.
- Runtime OpenAPI tương thích reviewed contract và SDK.
