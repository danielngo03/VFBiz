---
id: customer-portal-architecture
title: Kiến trúc Customer Portal
status: active
owner_role: engineering-lead
scope: customer-portal
when_to_read:
  - customer-bff
  - authentication
  - customer-session
context_anchors:
  customer-bff: "## Ranh giới"
  authentication: "## Login và session"
  customer-session: "## Logout và revocation"
tags:
  - nextjs
  - oidc
  - security
revision: 3
review_date: 2026-08-24
supersedes: []
---

# Kiến trúc Customer Portal

## Ranh giới

Keycloak là Identity Provider và MFA authority. PostgreSQL là system of record
cho customer business state, consent, garage, authorization projection và audit.
Redis database riêng của Customer Portal là encrypted token vault có TTL; mất
vault phải trả `401` và yêu cầu đăng nhập lại, không được tạo identity giả hoặc
fallback sang token trong browser.

Portal dùng Next.js App Router. Server Component mặc định gọi server-only DAL;
DAL gắn access token khi gọi NestJS. Server Action xử lý form mutation. Route
Handler chỉ dành cho callback, logout, back-channel hoặc browser-specific BFF
operation. `proxy.ts` chỉ redirect tối ưu; DAL và NestJS mới là security
boundary.

## Cấu trúc và dependency

Portal dùng hybrid feature-first:

```text
app -> features -> platform
app -> components
features -> components
```

- `app` chỉ giữ route convention, shell và composition.
- `features/<capability>` sở hữu component, model, schema, Server Action và
  style của capability đó.
- `platform/api`, `platform/auth`, `platform/config` và `platform/session`
  chứa infrastructure dùng xuyên feature và không được import ngược `features`
  hoặc `app`.
- `@vfbiz/portal-session-core` chỉ cung cấp primitive security đã được kiểm thử
  chung như exact-origin/CSRF, private response và versioned encryption
  envelope. Realm, cookie, timeout, MFA và lifecycle vẫn thuộc portal này.
- `components/ui`, `components/layout` và `components/feedback` chỉ chứa thành
  phần có nhiều consumer thật.

Page phải render navigation và heading ngay. Dữ liệu chậm được stream trong
feature-owned async component qua `Suspense`; expected upstream failure được
map thành result state. `error.tsx` chỉ dành cho lỗi không dự kiến.

## Contract

- `public-v1`: NestJS resource API `/api/v1`, dùng bởi server DAL và generated
  client.
- `customer-bff-v1`: `/api/auth` và `/bff`, dùng bởi browser cùng origin.

Không đưa provider redirect và business resource vào cùng security scheme.

## Login và session

1. BFF tạo state, nonce và PKCE verifier; attempt có TTL 10 phút.
2. Keycloak hoàn tất registration/login/required action.
3. Callback verify chữ ký ID token, issuer, audience, nonce, `sid`,
   `email_verified` và authentication evidence.
4. BFF sinh opaque session ID cùng CSRF token, mã hóa token set bằng
   AES-256-GCM rồi ghi Redis.
5. Browser chỉ nhận opaque cookie. BFF gắn access token khi gọi NestJS.
6. Refresh dùng lease theo session và luôn lưu refresh token mới khi Keycloak
   rotation trả về.

Session có absolute timeout, idle timeout và secondary index theo subject cùng
Keycloak `sid`. User-agent, device label và network hint chỉ phục vụ UX/audit,
không phải device identity hoặc authorization factor.

## Logout và revocation

Logout chủ động xóa local vault record ngay cả khi provider timeout; kết quả
provider nói rõ `confirmed`, `pending` hoặc `retry_required`. Khi lần gọi trực
tiếp thất bại, refresh token được mã hóa thành reconciliation job có TTL trong
Redis. Worker có machine credential gọi
`POST /api/internal/provider-revocations`, giữ single-flight lease và retry với
bounded exponential backoff. Worker credential không được đưa vào browser.

Keycloak back-channel
logout gửi signed logout token tới `/api/auth/backchannel-logout`; BFF verify
issuer, audience, event, `jti` và chống replay trước khi xóa session theo `sid`
hoặc subject.

Access token chỉ sống 5 phút. Resource API không tin cookie của portal và vẫn
verify bearer token. BFF gọi resource API với `credentials: omit`, bearer token
lấy từ vault và không forward browser `Cookie`. Redis retry queue không thay
thế durable audit/evidence ở PostgreSQL; scheduler, retention và alert phải
được cấu hình trước production release.

## Redis production profile

Auth session store phải tách khỏi cache plane:

- `noeviction`; write failure phải fail closed.
- TLS, ACL theo service, network isolation và secret rotation.
- AES-256-GCM payload encryption bằng key từ secret manager.
- HA/replication và capacity alert; AOF/backup tùy RTO/RPO đã duyệt.
- Cache giá/trạm có TTL và eviction riêng, không dùng chung auth token vault.

Redis không phải audit system of record. PostgreSQL chỉ lưu session projection
đã tối thiểu hóa và revocation evidence; không lưu access token, refresh token,
password, password hash, OTP seed hoặc recovery code.

## Security invariants

- Mọi state-changing route kiểm exact Origin và synchronizer CSRF token.
- Return URL chỉ là same-origin relative path.
- Token, cookie, CSRF token và raw IP không xuất hiện trong log.
- Back-channel endpoint giới hạn content type/body, verify JWT và chống replay.
- Cookie dùng `Secure` ở HTTPS production; local HTTP không bật `Secure`.
- Không dùng browser fingerprint làm quyền truy cập.
- Protected response dùng `private, no-store`.
- API lỗi được map có correlation; ETag/idempotency không bị bỏ qua qua BFF.
- Browser không gọi NestJS bằng bearer token và không nhận raw provider payload.
