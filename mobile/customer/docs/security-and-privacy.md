# Security và privacy

## Tài sản cần bảo vệ

OIDC credential, subject identity, profile, garage relationship, session/security
status, consent/privacy request, correlation evidence và release channel.

## Control mặc định

- System-browser PKCE; public client không secret.
- SecureStore device-only cho credential nhỏ; subject-partitioned SQLite.
- Android backup bị tắt ở app level trong phase 1; SecureStore exclusion rules
  vẫn được sinh như defense-in-depth. Signed artifact và restore/device-transfer
  test phải chứng minh SQLite, cache, temp và credential không được phục hồi.
- HTTPS bắt buộc ở preview/production config; API path allowlist và Bearer boundary.
- Camera/location/notification/Bluetooth/contacts bị block trong phase 1.
- Telemetry scrub token, email, VIN, display name, query/support content.
- No remote font/asset/analytics và không commit production data.

## Abuse/failure cần test

Callback hijack/replay/state mismatch, rooted-device extraction limitation,
refresh rotation race, cross-account cache bleed, stale authz UI, offline blind
retry, screen capture/log leakage, malicious deep link và compromised OTA.

SecureStore/OS protection không biến thiết bị thành trusted server. API phải luôn
authorize object/subject. Device compromise, jailbreak/root detection và local DB
encryption cần threat-model/ADR riêng khi data classification mở rộng.

Apple privacy manifest và Google Data Safety phải được tạo từ dependency/data-flow
evidence, không copy template. Security Owner và Privacy Owner phải review trước
production build; Legal/Brand duyệt asset/copy liên quan.
