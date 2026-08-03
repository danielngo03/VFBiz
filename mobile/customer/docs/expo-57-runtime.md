# Expo SDK 57 runtime

Baseline được pin: Expo 57.0.9, React Native 0.86.2, React 19.2.3 và Node tối
thiểu 22.13.0. Package Expo-native dùng version từ SDK 57 bundled module map;
không tự nâng một native module ngoài compatibility set.

Development build là runtime phát triển chuẩn vì app cần native SecureStore,
SQLite, OAuth callback, CNG/config plugins và release rehearsal. Expo Go chỉ có
thể dùng để thử component không phụ thuộc native boundary, không phải acceptance.

`app.config.ts` là dynamic config duy nhất. Config production bắt buộc HTTPS và
OIDC client ID; app config chỉ chứa public identifier/URL. Secret/signing material
không dùng prefix `EXPO_PUBLIC_*` và không vào bundle.

Typed routes được bật. Metro config không tồn tại vì SDK 57 tự nhận npm monorepo;
chỉ thêm `metro.config.js` khi có lỗi quan sát được và phải ghi lý do/rollback.
`ios/`/`android/` là generated output, bị git-ignore trong phase 1.

OTA được cấu hình `enabled: false`. `runtimeVersion` fingerprint có sẵn cho
compatibility evidence nhưng không tạo production update authority.
