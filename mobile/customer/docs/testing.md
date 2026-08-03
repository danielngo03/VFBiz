# Chiến lược kiểm thử

## Test pyramid

- Unit: config, auth reducer/token refresh helpers, Problem mapping, freshness,
  namespace, outbox policy, telemetry scrub.
- Component: Home/Garage/Account và fresh/stale/unknown/offline/restricted states.
- Contract: chỉ import generated public client, path/type drift fail compile.
- Storage: subject/environment isolation, migration, outbox/idempotency, logout.
- Accessibility: label/order, large text, reduced motion, contrast.
- Maestro: callback, garage smoke, logout persistence wipe, offline/online.

Development build acceptance chạy cả iOS/Android. Auth E2E dùng dedicated mock/
development realm, không record production credential. Network matrix gồm slow,
drop-before-response, token expiry, clock skew và 401/403/409/412/429/5xx.

PR checks: lint, typecheck, Jest, contract/token drift, Expo Doctor, app config
validation, forbidden imports, secret/dependency scan. Native/config-plugin diff
phải chạy prebuild trong throwaway workspace; generated native dirs không commit.

Maestro flows có `REQUIRE_MOCK_AUTH`; lane chỉ chạy khi CI cung cấp mock identity
fixture. Flow không có fixture bị report skipped, không được tuyên bố passed.

## Toolchain finding 2026-07-30

`expo export --platform all` đã bundle thành công. CNG iOS prebuild và CocoaPods
install cũng thành công trên Xcode 26.2, nhưng development build dừng trong
`expo-modules-jsi@57.0.4` tại `JavaScriptCodable+Date.swift` với Swift 6.2.3:
“type of expression is ambiguous”. Đây là dependency/toolchain blocker, không
phải acceptance pass. Không patch `node_modules`, không commit generated `ios/`
và không đổi Expo package ngoài compatibility matrix chỉ để che lỗi. Lane iOS
cần upstream-compatible patch hoặc approved Xcode/EAS image evidence rồi chạy
lại build và visual QA.

Android development build đã biên dịch thành công bằng Gradle 9.3.1 với Android
Studio JBR, được cài lên Pixel 10 emulator dưới application id
`com.vfbiz.customer.dev`, kết nối Metro qua `adb reverse tcp:8081 tcp:8081` và
render thành công Customer sign-in route. Đây là native runtime smoke evidence;
không thay thế auth callback, storage wipe hoặc Maestro acceptance.
