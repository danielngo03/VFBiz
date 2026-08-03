# Ranh giới riêng của Customer Mobile

Customer là native app độc lập với app identifier, OIDC client, local data,
build/update channel, telemetry và incident blast radius riêng. Tài liệu này chỉ
áp dụng cho Customer, không được dùng làm policy ngầm cho Workforce.

```text
Customer app -> system browser -> vfbiz-customer realm -> native callback
Customer app -> generated public client -> NestJS API authority
NestJS API -> governed providers/AI/data systems
```

App không gọi Next.js BFF, database, Drupal, AI provider hoặc Keycloak Admin API.
App chỉ giữ presentation state, credential cần thiết và cache có thể xóa/tái tạo;
server vẫn là system of record.

Cache Customer phân vùng theo app, environment, issuer, subject, market và schema
version. Logout xóa credential, query cache, SQLite partition, outbox, pending
payload và temp files. Không có credential/cache dùng chung với app khác.

`/mobile` chỉ chứa các app directory. Mọi product/runtime/governance truth của
Customer nằm dưới `mobile/customer`; không đặt README/docs/provider adapter ở
container level.
