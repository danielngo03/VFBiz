---
id: VFBIZ-0203
title: Xây nền tảng VFBiz Customer Mobile bằng Expo 57
status: active
mode: controlled
priority: P0
owner_team: mobile-experience
accountable_role: engineering-lead
primary_workspace: mobile
affected_workspaces:
  - mobile
  - design-tokens
  - root
allowed_paths:
  - mobile/customer
  - packages/design-tokens
  - docs/work/items/VFBIZ-0203.md
  - docs/work/plans/VFBIZ-0203.md
  - docs/decisions/0008-mobile-customer-expo57.md
  - package.json
  - package-lock.json
  - WORK.md
depends_on: []
controlled_signals:
  - authentication
  - pii
  - dependency-policy
  - production-release
exclusive_resources:
  - customer-mobile-app-config
  - customer-mobile-release-config
  - native-dependency-registry
  - mobile-token-output
  - customer-mobile-auth-callback
required_checks:
  - npm run verify --workspace @vfbiz/design-tokens
  - npm run typecheck --workspace @vfbiz/mobile-customer
  - npm run test --workspace @vfbiz/mobile-customer
  - npm run native-config:check --workspace @vfbiz/mobile-customer
  - npm run doctor --workspace @vfbiz/mobile-customer
  - npm run governance:check
revision: 5
review_date: "2026-08-30"
updated_at: "2026-07-30T10:07:42.119Z"
---

# Outcome

Tạo Customer Mobile foundation chạy được trên Expo SDK 57, có kiến trúc route,
design token native, auth/session boundary, cache phân vùng theo subject, API
contract boundary, bộ kiểm tra và tài liệu vận hành đủ để tiếp tục các vertical
slice Account, Garage, Privacy và Security.

## Constraints

- Chỉ thay đổi Customer Mobile; không sửa `mobile/workforce` hoặc backend runtime.
- Expo Go không phải runtime phát triển chính; dùng development build, CNG và
  Expo Router với route tree tại `src/app`.
- Không commit `ios/`, `android/`, secret, production data hoặc brand asset chưa
  được Brand/Legal phê duyệt.
- Mobile chỉ gọi generated public API client; không gọi BFF, database, Drupal,
  AI provider hoặc Keycloak Admin API.
- ADR do agent soạn vẫn cần human Architect chấp thuận trước production release.

## Done when

- `mobile/customer` được đăng ký trong npm workspace và có Expo 57 app shell,
  typed routes, protected owner group, environment validation và EAS profiles.
- Native design-token output được generate và kiểm tra drift từ canonical token.
- Auth/session, SecureStore, SQLite subject partition, API Problem mapping và
  logout wipe có implementation foundation cùng test quan sát được.
- Home, Garage và Account hiển thị đúng các trạng thái freshness/offline và
  Assistant bị khóa khi không có capability.
- Customer docs, app governance, agent operating model, ADR, ExecPlan và
  release/runbook nằm hoàn toàn trong Customer boundary; `/mobile` không giữ
  README/docs/provider adapter chung và `mobile/workforce` không bị thay đổi.
- Các required check có bằng chứng thực thi; release vẫn bị khóa nếu thiếu
  Architect, Security, Privacy hoặc Release Owner gate.

## Checkpoint

- Customer foundation, app-specific docs/governance, native token
  output, auth/API/storage boundaries, route shell và tests đã được triển khai.
- iOS/Android static export bundling thành công; không có thay đổi dưới
  `mobile/workforce` hoặc backend runtime.
- Người dùng đã yêu cầu bỏ toàn bộ shared instruction/docs tại `/mobile`; exact
  next implementation đang chuyển các policy có consumer Customer vào app root.
- Acceptance vẫn bị chặn bởi React 19.2.3 (Expo 57) tồn tại cạnh React 19.2.8
  của web portals trong npm monorepo và global dependency-risk snapshot chưa
  được cập nhật/duyệt cho lockfile mới.
- Exact next action: Architect/Engineering Lead chọn React/package isolation
  strategy và Security Owner xử lý dependency snapshot/advisory gate; sau đó
  chạy lại Expo Doctor và governance check.

## Evidence

- [x] `npm run verify --workspace @vfbiz/design-tokens` — 3/3 tests pass,
  generated native/CSS outputs không drift.
- [x] `npm run typecheck --workspace @vfbiz/mobile-customer` — pass với
  TypeScript 6.0.3 strict/exact optional types.
- [x] `npm run test --workspace @vfbiz/mobile-customer` — 14 suites, 24/24 tests
  pass, gồm claim validation, route guard, typed-route generation, freshness và
  partial logout wipe.
- [ ] `npm run doctor --workspace @vfbiz/mobile-customer` — 19/20 pass; duplicate
  React 19.2.3/19.2.8 giữa Mobile và web workspace còn mở.
- [ ] `npm run governance:check` — maturity pass; dependency-risk snapshot fail
  vì lockfile digest mới chưa có global Security approval.
- [x] `npm run lint` và `npm run boundaries` cho Customer — pass.
- [x] `npm run native-config:check` — production scheme/ATS/backup/forbidden
  permission assertions pass bằng Expo native introspection.
- [x] `expo export --platform all` — iOS và Android bundle thành công.
- [x] `git diff --check` và Workforce untouched assertion — pass.

## Open decision and gate matrix

| Gate/decision | Human authority | Evidence | State | Exact next action |
| --- | --- | --- | --- | --- |
| Expo/CNG architecture | architect | ADR-0008, Expo config/export | proposed | Architect accept/reject ADR |
| React dependency isolation | engineering-lead + architect | Expo Doctor duplicate report | open | choose supported workspace isolation/version strategy |
| Native auth/cache privacy | security-owner + privacy-owner | risk review, auth/storage tests | review | close critical/high findings with new evidence |
| Global dependency risk | security-owner + Agent Platform owner | npm audit, lockfile snapshot | open | update/review global risk snapshot in its owning work item |
| Customer experience | product-owner + design-lead | route/UI/accessibility review | review | accept phase-1 journey or return findings |
| Store/OTA release | release-owner | signed build/rollout/rollback | locked | remain locked until all prior gates close |

### ready — 2026-07-30T09:35:40.572Z

Người dùng đã phê duyệt triển khai Customer Mobile Foundation trong task ngày 2026-07-30; production release vẫn cần các human authority gate đã khai báo.

### active — 2026-07-30T09:35:40.860Z

Bắt đầu delivery theo allowed paths; không sửa Workforce hoặc backend runtime.

### blocked — 2026-07-30T10:00:31.098Z

Code-complete; acceptance bị chặn bởi duplicate React 19.2.3/19.2.8 trong npm monorepo và global dependency-risk snapshot/advisory gate cần Architect, Engineering Lead và Security Owner quyết định ngoài allowed paths hiện tại.

### active — 2026-07-30T10:07:42.119Z

Người dùng mở lại delivery để sửa app ownership boundary: xóa docs/instructions ở /mobile, chuyển toàn bộ policy có consumer Customer vào mobile/customer và thực hiện independent agent reviews.

### active — 2026-07-30T10:45:00.000Z

Ba lane độc lập đã hoàn tất architecture/organization, acceptance và risk review.
Đã sửa fail-closed restore/logout/401, claim binding, callback scheme theo môi
trường, Android backup rule, native permission block, telemetry và typed-route
generation. Preview/production tiếp tục khóa do React/dependency/human gates.
