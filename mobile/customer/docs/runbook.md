# Customer Mobile runbook

## Auth failure spike

1. Dừng rollout/update; xác nhận environment, issuer, client ID, redirect URI và
   identity health bằng synthetic account.
2. So sánh app version/build/runtime và correlation ID; không yêu cầu user gửi
   token/screenshot chứa PII.
3. Nếu refresh/callback regression, rollback compatible update hoặc giữ store
   build trước; remote logout claim chỉ theo API evidence.

## API/error spike

Tách network, 401, 403, 409/412, 429 và 5xx. 401 kiểm issuer/token lifecycle;
403 kiểm authorization revision; 409/412 giữ user edits và hiện conflict; 429
backoff; 5xx giữ stale cache có label. Không blind retry mutation.

## Cache/privacy incident

Khóa capability/persisted hydration, kích hoạt subject-partition wipe, bảo toàn
minimal scrubbed evidence và báo Security/Privacy. Không tự mở database production
hoặc copy customer payload ra khỏi approved environment.

## Crash/update incident

Dừng staged rollout, xác định native build vs OTA runtime mismatch, rollback/cancel
update nếu đã rehearsal, hoặc phát store build mới. Không gửi OTA vượt runtime
compatibility để chữa native crash.

## Recovery verification

Chạy cold launch, sign-in callback, profile/garage read, offline label, logout
wipe và relaunch trên cả iOS/Android. Chỉ Release Owner tiếp tục rollout; outcome
validated cần theo dõi signal sau release.
