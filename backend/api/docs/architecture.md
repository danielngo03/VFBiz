---
id: api-architecture
title: Kiến trúc API Platform
status: active
owner_role: engineering-lead
scope: api
when_to_read:
  - api-boundary
  - public-contract
  - authorization
  - integration
tags:
  - nestjs
  - architecture
revision: 2026-07-23.5
review_date: 2026-08-22
supersedes: []
---

# Kiến trúc API Platform

## Boundary

API Platform là authority duy nhất cho public API, customer/workforce identity
projection, authorization, transaction và side effect. Drupal chỉ giữ CMS/SEO;
AI Platform chỉ đưa ra grounded answer hoặc tool proposal.

## Dependency rule

```text
presentation -> application -> domain
infrastructure -> application/domain ports
composition root -> all layers
```

Chiều ngược lại bị cấm. Context khác chỉ giao tiếp qua public application port,
versioned contract hoặc outbox event. Không dùng `common/models` hay
`common/services` làm vùng chứa tùy tiện.

Danh sách bounded context đã duyệt và quy tắc đặt code nằm trong
`backend/api/AGENTS.md`. Bounded context cấp cao mới là thay đổi ranh giới
repository và cần root ADR; một feature, endpoint hoặc provider thì không.
Composition root hiện chỉ nạp `access`, `customer` và `product`.
`/api/v1/health/live` chỉ kiểm tra process; `/api/v1/health/ready` thực hiện
PostgreSQL probe tối thiểu và trả `503` mà không lộ database error khi dependency
không sẵn sàng.
`customer` sở hữu Profile/Consent/DSAR; `product` sở hữu public read model của
một active Vehicle Catalog release. Source code thử nghiệm của `engagement` và
`mobility` không đồng nghĩa capability đang active: chúng không được nạp, yêu
cầu secret hoặc xuất hiện trong public contract cho tới work item riêng.
Boundary tương lai không được biểu diễn bằng `@Module({})` rỗng.

## Contract boundary

- Nest sinh runtime OpenAPI description; root contract đã review và generated SDK
  là integration artifact dùng chung.
- Public `/api/v1` chỉ nhận thay đổi additive trừ khi có versioning decision
  khác đã được chấp nhận. Không che giấu breaking change bằng cách đổi tên DTO.
- HTTP DTO và presenter là adapter. Không phơi bày domain entity hoặc Prisma
  record làm wire model.
- Error dùng RFC Problem Details và correlation ID. Mutation có thể retry phải
  idempotent tại application boundary.

## Persistence and integration boundaries

PostgreSQL lưu API-owned state, governed projection, audit, idempotency và
outbox record. `data-model.md` là nguồn chuẩn cho ownership, retention và
migration; `integration-adapters.md` là nguồn chuẩn cho provider adapter,
webhook và reconciliation.

Dữ liệu nguồn thiếu hoặc stale phải trả về trạng thái unavailable/freshness
rõ ràng. Provider timeout không được biến fixture, model output hay dữ liệu
synthetic thành business authority.
