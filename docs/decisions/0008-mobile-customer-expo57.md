---
id: adr-0008
title: Customer Mobile dùng Expo 57, CNG và app boundary độc lập
status: proposed
owner_role: architect
scope: cross-system
when_to_read:
  - mobile-customer-foundation
  - native-dependency
  - mobile-release
tags:
  - adr
  - mobile
  - expo
revision: 1
review_date: 2026-08-30
supersedes: []
---

# ADR-0008: Customer Mobile dùng Expo 57, CNG và app boundary độc lập

Date: 2026-07-30

## Context

VFBiz cần một Customer Mobile app có native-quality UX, OIDC PKCE, offline cache,
observability và release discipline, trong khi repository hiện mới có planning
boundary. Runtime phải hỗ trợ native escape hatch mà không bắt team sở hữu thủ
công Xcode/Gradle project ngay từ phase đầu.

## Decision

Customer Mobile dùng Expo SDK 57.0.9, React Native 0.86, React 19.2.3, Expo
Router tại `src/app`, development builds, Continuous Native Generation và EAS
Build/Update/Workflows. `ios/` và `android/` không commit trong phase 1; native
change đi qua app config/config plugin. Customer là app root độc lập tại
`mobile/customer` và sở hữu toàn bộ README, instructions, provider adapter,
product/runtime/governance docs của chính app. `/mobile` chỉ là filesystem
container, không phải documentation hoặc instruction boundary.

## Alternatives

- Bare React Native ngay từ đầu: chưa có vendor SDK hoặc native lifecycle nào
  chứng minh cần chi phí ownership này.
- Một mobile app chung cho Customer/Workforce: làm lẫn realm, permission, release
  authority và blast radius; không được chọn.
- Expo Go làm runtime chính: không đáp ứng OAuth/development client/native module
  và release rehearsal của foundation này.

## Consequences

- Có thể scaffold nhanh, typed routing, CNG và EAS tooling nhất quán trong
  monorepo; vẫn viết Expo Module Swift/Kotlin khi có consumer thật.
- Native dependency/config-plugin trở thành controlled change và phải có
  compatibility, permission, privacy, rollback evidence.
- Production OTA bị khóa cho tới khi có runtimeVersion policy, code signing,
  staged rollout và rollback rehearsal.
- Nếu OEM/BLE/CarPlay/Android Auto proof-of-concept chứng minh CNG không bền vững,
  Architect có thể mở ADR chuyển sang native-project ownership.

## Approval

Human decision owner: `architect`. Người dùng đã yêu cầu triển khai foundation
theo quyết định này ngày 2026-07-30; ADR vẫn ở trạng thái `proposed` và không tạo
production release authority cho agent.
