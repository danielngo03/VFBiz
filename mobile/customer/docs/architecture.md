# Kiến trúc Customer Mobile

## Layer và dependency direction

```text
src/app routes/layouts
      -> features + design
      -> state/query/mutation
      -> platform API/auth/storage/device
      -> generated contracts + Expo modules

domain <- features/state/platform adapters
```

`src/app` chỉ composition/navigation. Domain không import Expo/React Native.
Platform adapter không đưa provider concept vào domain. Feature screen không tự
khởi tạo database, token store hoặc raw fetch.

Root layout mount theo thứ tự Gesture -> Query -> Theme -> Auth -> Router.
Authenticated routes nằm trong `(owner)`; anonymous session bị redirect trước
khi child route render. Server vẫn là authority; local data là cache/outbox có
thể xóa và rebuild.

## Trust boundaries

System browser sở hữu password/OTP/WebAuthn. SecureStore giữ credential nhỏ.
SQLite giữ cache/outbox có namespace. API transport chỉ chấp nhận `/api/v1/*`,
Bearer token và RFC Problem Details. AI, Drupal, DB, BFF và Keycloak Admin không
có adapter trong app.

## Native ownership

CNG tạo `ios/`/`android/` từ `app.config.ts` và config plugins. App root là nơi
chạy EAS command. Native module chỉ được thêm sau dependency review và consumer
thật; chuyển sang native-project ownership cần ADR mới cùng proof-of-concept.

## Team interfaces

| Trigger | Owner/authority cần phối hợp | Evidence/artifact |
| --- | --- | --- |
| Public API/contract change | API Foundation + Architecture & Integration | generated contract, compatibility check, ADR nếu khó đảo ngược |
| Realm/client/callback/MFA | Identity Experience + Security Owner | registered native client, threat evidence, auth E2E |
| Native/design token change | Identity Experience + Design Lead | canonical token revision, visual/accessibility review |
| Cache/PII/offline change | Privacy + Security + Data Owner | classification, wipe/isolation tests, retention decision |
| Dependency/lockfile | Agent Platform + Security Owner | lockfile, audit/risk snapshot, rollback |
| Build/OTA/store | Reliability Engineering + Release Owner | immutable artifact, rollout/rollback evidence |

Mobile Experience vẫn là writer duy nhất cho Customer runtime. Team phối hợp
không trở thành co-writer trừ khi có work item/allowed paths disjoint riêng.
