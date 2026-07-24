---
id: workforce-portal-architecture
title: Kiến trúc Workforce Portal
status: active
owner_role: engineering-lead
scope: workforce-portal
when_to_read:
  - workforce-admin
  - authentication
  - authorization
context_anchors:
  workforce-admin: "## Mục đích"
  authentication: "## Session và token vault"
  authorization: "## Ranh giới runtime"
tags:
  - nextjs
  - workforce
  - security
revision: 2
review_date: 2026-08-24
supersedes: []
---

# Kiến trúc Workforce Portal

## Mục đích

Workforce Portal là giao diện và Backend for Frontend (BFF) dành cho nhân sự.
Portal không sở hữu workforce identity, role, capability, assignment, audit hay
business data.

## Ranh giới runtime

```text
Browser
  → Next.js BFF (opaque session cookie)
    → server-side token vault
      → NestJS Workforce API
        → Authorization Platform và domain application service
```

- Keycloak xác thực identity, realm, audience và MFA.
- Next.js điều phối OIDC Code + PKCE, session và server-side API calls.
- NestJS xác minh token, entitlement, organizational scope và object policy.
- PostgreSQL của API là nguồn chuẩn cho authorization data.
- Redis chỉ là session/token-vault/cache implementation; cache không phải
  authority.

## Quy tắc Next.js

- Server Components là mặc định.
- Client Component chỉ bao quanh interaction thật; không đưa access token,
  refresh token hoặc trusted entitlement sang client.
- Mọi adapter trong `src/platform` chạy phía server phải import `server-only`.
- Proxy chỉ được dùng để redirect sớm theo opaque session cookie. Proxy không
  xác thực capability và không thay thế DAL/API authorization.
- Route Handler hoặc Server Action có side effect phải kiểm session, origin,
  CSRF, input schema, idempotency và expected version.
- Workforce response dùng `Cache-Control: private, no-store`.
- Error hiển thị cho người dùng không chứa token, policy internals hoặc raw
  upstream response.

## Session và token vault

Browser giữ duy nhất opaque session ID. Cookie phải `HttpOnly`,
`SameSite=Lax`, có `Secure` trên HTTPS và được rotate khi login, MFA hoặc
entitlement revision thay đổi.

Absolute lifetime và idle timeout là hai policy độc lập. Redis giữ activity
timestamp ở key riêng để request thường có thể touch idle state mà không
decrypt/re-encrypt hoặc ghi đè token set đang được refresh; việc liệt kê các
thiết bị không được làm mới activity của các phiên khác.

Access/refresh token chỉ tồn tại trong token vault phía server. Contract không
quyết định Redis key hoặc encryption implementation; implementation phải có
expiry, revoke, rotation và audit không chứa token.

Mỗi subject có session index trong Redis để hỗ trợ danh sách thiết bị và
`sign out all devices`. Record đã mã hóa chỉ giữ opaque ID, device label,
sanitized user-agent, optional network prefix, verified-email/MFA evidence và
timestamps. Không trả access/refresh token hoặc raw IP cho browser.

Primitive dùng chung nằm trong `@vfbiz/portal-session-core`; package này không
được sở hữu realm, capability hoặc policy nghiệp vụ. Refresh chỉ được ghi token
mới khi session gốc vẫn tồn tại và chưa có logout fence, ngăn request refresh
đang chạy làm sống lại session đã bị thu hồi.

`mfaSatisfied` là bằng chứng của phiên hiện tại. Portal không đọc trực tiếp
credential inventory của Keycloak; vì vậy `mfaConfigured` chỉ là `true` khi
phiên đã chứng minh MFA, còn thiếu evidence phải trả `null` thay vì suy đoán.

Network prefix chỉ được đọc từ forwarding header khi
`WORKFORCE_TRUST_PROXY_HEADERS=true` và hạ tầng bảo đảm proxy đã xóa header do
client tự gửi. Mặc định local là `false`, vì lưu IP giả còn nguy hiểm hơn không
lưu.

## Dependency rule

```text
app → features → platform
app → components
features → components
platform không import app hoặc features
```

`app` chỉ compose route, shell và Suspense boundary. Feature sở hữu presentation
model, async panel, skeleton và mutation của capability đó. `platform` sở hữu
API transport, OIDC, config và session vault; không chứa business presentation.
Portal không tự định nghĩa capability catalog.

## Trạng thái implementation

- OIDC callback và encrypted Redis token vault nằm trong `src/platform`.
- Workforce transport dùng types từ generated `@vfbiz/workforce-api-client` và
  runtime validation trước khi dữ liệu đi vào feature.
- Callback bắt buộc verified email và MFA; refresh dùng distributed
  single-flight lease. `/api/auth/security` và `/api/auth/sessions` cung cấp
  assurance, device list và logout-all mà không lộ token.
- Role, assignment, approval và audit hiện là read-only Server Component.
- Response từ Workforce API được runtime-validate và chỉ giữ field thuộc
  contract trước khi render.
- Mutation runtime chưa được mở. Khi triển khai phải bổ sung server-side
  idempotency, CSRF/origin check, expected version và maker-checker E2E thay vì
  gọi API trực tiếp từ Client Component.

## Streaming và lỗi

Route page render heading và navigation ngay. Mỗi bảng async dùng một
`Suspense` boundary với skeleton do feature sở hữu. Không tạo `loading.tsx` chỉ
để hiển thị một dòng chữ. Expected states được render thành result state;
`error.tsx` chỉ bắt lỗi ngoài dự kiến và không hiển thị raw upstream error.
