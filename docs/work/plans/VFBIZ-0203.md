---
id: plan-VFBIZ-0203
title: ExecPlan VFBiz Customer Mobile Foundation bằng Expo 57
status: active
owner_role: engineering-lead
scope: cross-system
when_to_read:
  - VFBIZ-0203
tags:
  - mobile
  - customer
  - expo
revision: 1
review_date: 2026-08-30
supersedes: []
---

# Mục đích và kết quả quan sát được

Thiết lập một Customer Mobile foundation production-shaped trên Expo SDK 57,
nhưng chỉ mở các capability đã có backend authority. Kết quả phải cài dependency
được từ root workspace, typecheck/test được, tạo development build được và có
boundary rõ cho auth, API, cache, UI, accessibility, telemetry và release.

## Phạm vi, ranh giới và phần không làm

- Được sửa: `mobile/customer/**`, xóa các container-level files dưới `mobile/`,
  `packages/design-tokens/**`, work item/plan/ADR và root workspace/lockfile.
- Không sửa `mobile/workforce`, backend runtime, public API contract hoặc identity
  realm configuration trong work item này.
- Không bật notification, camera, location, Bluetooth, vehicle control, charging
  hoặc production OTA.
- Không nhận asset VinFast từ web; chỉ dùng placeholder trung tính.

## Tiến độ

- [x] 2026-07-30: xác nhận Customer-only boundary và Expo 57/CNG/dual-runtime
  principles từ plan do người dùng phê duyệt triển khai.
- [x] 2026-07-30: tạo work item, ExecPlan và ADR draft.
- [x] 2026-07-30: đăng ký npm workspace và khóa Expo/RN/React/toolchain versions.
- [x] 2026-07-30: dựng Expo Router shell, provider composition và protected owner routes.
- [x] 2026-07-30: dựng native tokens, UI primitives và accessibility baseline.
- [x] 2026-07-30: dựng auth/session, API, storage/cache/outbox và logout wipe foundation.
- [x] 2026-07-30: dựng Customer vertical slice foundation và Maestro smoke flows.
- [ ] Hoàn tất Expo Doctor, dependency/security review và human acceptance gates.

## Phát hiện và bất ngờ

- Repository đang có nhiều thay đổi AI/GCP chưa commit; toàn bộ lane này phải
  giữ nguyên các thay đổi đó và chỉ chạm allowed paths.
- `packages/design-tokens` hiện chỉ phát CSS/JSON với giá trị `rem`; native output
  cần chuyển dimension sang số React Native mà không thay primitive names.
- `mobile/customer` hiện trống, vì vậy có thể dựng cấu trúc đúng ngay từ đầu mà
  không cần migration runtime.
- npm hoist React 19.2.8 của web portals tại root, trong khi Expo 57 pin React
  19.2.3 tại app root. Bundle hoạt động nhưng Expo Doctor đúng khi giữ release
  gate đỏ cho duplicate React resolution.
- Production audit mới quan sát 10 high/11 moderate trong production dependency
  graph, chủ yếu tooling transitives của React Native/Expo; `audit fix --force`
  đề xuất downgrade/breaking change nên bị từ chối theo policy.

## Nhật ký quyết định

- 2026-07-30 — User/Product direction: chỉ triển khai Customer Mobile trong
  VFBIZ-0203; Workforce nằm ngoài scope.
- 2026-07-30 — Engineering recommendation: Expo SDK 57, React Native 0.86,
  React 19.2.3, Expo Router, development builds và CNG.
- 2026-07-30 — Architecture boundary: `src/app` chỉ composition; feature/domain/
  platform/design/state nằm ngoài route tree.
- 2026-07-30 — User architecture correction: `/mobile` chỉ là container; README,
  AGENTS, provider adapter và mọi docs thuộc Customer phải nằm trong app root.
- 2026-07-30 — Security boundary: PKCE qua system browser, credential nhỏ trong
  SecureStore, structured cache trong SQLite và wipe theo subject khi logout.

## Các phase và allowed paths

1. Governance: work item, ExecPlan, ADR và Customer-only docs/governance.
2. Toolchain: root workspace, Customer package/config và lockfile.
3. Runtime: providers, routes, feature shell, platform boundaries và UI tokens.
4. Assurance: tests, Maestro, docs, Expo Doctor và governance checks.

Mọi phase dùng cùng allowed paths trong VFBIZ-0203; app config, release config,
native dependency registry, token output và auth callback là exclusive resource.

## Validation và bằng chứng

- Design token verify: 3/3 pass; native values không chứa `rem`.
- Customer: TypeScript, ESLint, boundary check và 24/24 Jest tests pass.
- Expo public config schema pass; static export bundle iOS (3.9 MB HBC) và
  Android (4.1 MB HBC) thành công.
- Expo Doctor 19/20; duplicate React giữa Customer/Web còn mở.
- Governance dừng tại stale dependency-risk snapshot digest. Không sửa global
  snapshot hoặc chấp nhận advisory ngoài allowed path/authority.
- Không suy diễn production readiness từ bundle, typecheck hoặc test pass.

## Independent review record

- Organization/architecture explorer xác nhận không cần tạo thêm department hay
  runtime-agent authority; ownership hiện có đủ và được route trong Customer docs.
- Reviewer-verifier phát hiện typed routes chưa được CI generate và trạng thái
  freshness/negative tests còn mỏng; generator deterministic và các state/guard
  tests đã được bổ sung.
- Risk-reviewer phát hiện expiry/logout/claim/callback/backup/native-config và
  telemetry risks. Các mitigation trong Customer scope đã được triển khai; exact
  Keycloak registration, signed binary, dependency acceptance và release vẫn là
  human/cross-workspace gates, không được agent tự chấp thuận.

## Rollback và phục hồi

- Foundation chưa chứa migration server hoặc production data; rollback bằng cách
  loại workspace Customer và native generated outputs khỏi revision tương lai.
- CNG cho phép tái tạo native project; `ios/` và `android/` không phải nguồn thật.
- Production OTA mặc định khóa; không có rollback OTA nào được tuyên bố cho đến
  khi code signing và rehearsal có bằng chứng.

## Kết quả và retrospective

Foundation đạt code-complete trong phạm vi VFBIZ-0203 nhưng chưa
acceptance-complete. Release/outcome validation chưa bắt đầu; work item giữ gate
đỏ tới khi React isolation, dependency risk và human review được giải quyết.
