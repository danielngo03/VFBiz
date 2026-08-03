# Authentication và session

## Flow

```text
app -> system browser -> Keycloak vfbiz-customer realm
    -> Authorization Code + PKCE S256 -> app callback
    -> token exchange -> SecureStore -> Bearer API
```

Mobile là public OIDC client, không có client secret. Redirect URI, client ID và
environment phải exact-match registered native client. Password, OTP, recovery,
WebAuthn response và admin credential không đi qua app.

Mỗi environment có reverse-domain scheme riêng. ID token phải khớp issuer,
audience/authorized party, expiry và nonce. Credential lưu cục bộ còn được bind
với environment, issuer, client ID và market; mismatch phải xóa phiên fail-closed.

Auth state machine phân biệt restoring, anonymous, authenticating, authenticated,
refreshing, signing-out và error. PKCE verifier chỉ sống trong auth request.
Access/refresh/id token nhỏ được lưu `WHEN_UNLOCKED_THIS_DEVICE_ONLY`; profile,
garage và API payload không vào SecureStore.

Refresh token rotation thay credential atomically. Refresh failure fail closed:
xóa credential và về anonymous. Subject lấy từ token response đã validate claim để bind
local namespace; app không cho anonymous/shared cache.

Logout phase 1 xóa credential, SQLite cache/outbox/pending payload, query cache
và temp directory dù từng bước gặp lỗi; UI không tuyên bố remote logout khi chưa
có reconciliation. Wipe chưa hoàn tất ghi một marker tối thiểu trong SecureStore
và được thử lại trước credential restore ở lần mở app sau. Revoke-all/session
mutation cần online + explicit confirmation.
