# Navigation và deep link

## Route map

```text
/
/sign-in
/auth/callback
/(owner)/(tabs)             Home
/(owner)/(tabs)/garage
/(owner)/(tabs)/account
/(owner)/garage/:id
/(owner)/garage/add
/(owner)/account/{profile,security,sessions,privacy,consents}
/(owner)/support
/(owner)/assistant
```

Root index chỉ quyết định restore -> sign-in/owner. `(owner)/_layout` là policy
enforcement point, không phải mỗi screen tự kiểm tra auth. Bottom navigation chỉ
có Home, Garage, Account để giữ thao tác một tay và giảm chrome.

Private-use scheme phase 1 được tách theo bundle/environment:
`com.vfbiz.customer.dev`, `com.vfbiz.customer.preview` và
`com.vfbiz.customer`. Callback luôn giới hạn ở host/path `auth/callback`; Keycloak
phải đăng ký exact redirect URI tương ứng. Claimed HTTPS Universal/App Links là
đích ưu tiên sau domain ownership, association-file deployment và hijack tests.
Không dùng arbitrary return URL từ query string; post-login destination phải nằm
trong typed internal route allowlist.

Deep-link tests bao gồm cold/warm launch, callback cancel/error, expired state,
anonymous protected route, malicious scheme và environment mismatch.
