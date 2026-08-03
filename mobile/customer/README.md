# VFBiz Customer Mobile

Customer owner experience built with Expo SDK 57, React Native 0.86, React
19.2.3, Expo Router, development builds and Continuous Native Generation.

## Bắt đầu

Yêu cầu Node >= 22.13.0 và npm từ root lockfile. Tạo `.env.local` từ
`.env.example`, sau đó chạy từ repository root:

```bash
npm install
npm run start --workspace @vfbiz/mobile-customer
```

App dùng development build; Expo Go không phải môi trường chính. Native project
được tạo lại bằng prebuild và không commit trong phase 1.

Lần đầu trên mỗi simulator/emulator, cần tạo và cài development build trước:

```bash
npx expo run:ios
npx expo run:android
```

Sau khi binary `com.vfbiz.customer.dev` đã được cài, các vòng phát triển
TypeScript/JavaScript tiếp theo chỉ cần:

```bash
npx expo start
```

Phím `i` hoặc `a` trong Metro chỉ mở development build đã được cài; chúng không
tự tạo binary. Thông báo `No development build ... is installed` vì vậy có nghĩa
là cần chạy lệnh `expo run:*` tương ứng, không phải Metro hoặc Expo Router hỏng.

## Boundary

`src/app` chỉ chứa Expo Router layouts/routes. Reusable UI ở `src/design`, user
journey ở `src/features`, business vocabulary ở `src/domain`, device/provider
integration ở `src/platform`, server/local state ở `src/state`.

Phase 1 chỉ mở Home, Garage và Account dựa trên authority hiện có. Vehicle live
state, charging, location, control, notification và Assistant provider vẫn khóa.
Xem `docs/` để có source of truth chi tiết cho Customer app.

## Tài liệu và agent boundary

Customer tự sở hữu README, `AGENTS.md`, `CLAUDE.md`, product/architecture,
security, testing và release docs. `/mobile` không có instruction hoặc docs chung;
Workforce sẽ có bộ riêng khi work item Workforce bắt đầu.

Agent delivery đi qua `docs/agent-operating-model.md`: orchestrator định tuyến,
implementer viết trong allowed paths, reviewer/risk reviewer độc lập trả evidence,
human owner mới có quyền chấp thuận architecture, privacy/security và release.
