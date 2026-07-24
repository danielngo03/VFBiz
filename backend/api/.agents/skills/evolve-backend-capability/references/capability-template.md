# Template triển khai một capability NestJS

**Owner role:** Digital Platform Engineering Lead

**Status:** Active

**Revision:** 2026-07-22.1

**When to read:** bắt đầu một vertical slice trong `backend/api`.

Template này là checklist, không phải lý do để tạo folder rỗng. Code hiện
hữu có thể giữ cấu trúc phẳng hơn cho tới khi có refactor được phê duyệt;
không restructure code ngoài scope chỉ để khớp template này.

## 1. Work envelope

- Work ID, claim/run ID khi bắt buộc, owner context, allowed paths và base SHA.
- Outcome/acceptance, authorization rule, source/freshness, failure behavior.
- Contract classification: none, additive hoặc breaking.
- Exclusive lease: migration, OpenAPI, lockfile nếu bị tác động.

## 2. Cấu trúc khi thực sự có code

```text
src/modules/<context>/
├── domain/
│   ├── entities/<aggregate>.ts
│   ├── value-objects/<value>.ts
│   ├── policies/<policy>.ts
│   └── errors/<error>.ts
├── application/
│   ├── commands/<use-case>.command.ts
│   ├── queries/<use-case>.query.ts
│   ├── ports/<repository-or-provider>.port.ts
│   └── use-cases/<use-case>.ts
├── infrastructure/
│   ├── persistence/prisma-<aggregate>.repository.ts
│   ├── persistence/<aggregate>.mapper.ts
│   └── providers/<provider>.adapter.ts
├── presentation/http/
│   ├── <resource>.controller.ts
│   ├── dto/<operation>.request.dto.ts
│   └── presenters/<resource>.presenter.ts
├── <context>.module.ts
└── index.ts
```

Không tạo `models/`, `services/`, `utils/` hoặc `common/` chung chung. Router của
NestJS là controller; schema HTTP là DTO đã validate; schema database nằm trong
`prisma/models`; domain model nằm trong `domain`.

## 3. Thứ tự implementation

1. Test invariant/use case thất bại.
2. Domain model và application port/use case.
3. Prisma schema + migration mới, nếu cần.
4. Repository/provider adapter và mapper.
5. Controller, request DTO và presenter.
6. Authorization/object ownership, idempotency, transaction/outbox và audit.
7. Export OpenAPI, compatibility check và generated SDK.
8. Unit, PostgreSQL integration, negative authorization, contract, E2E, build.

## 4. Evidence khi kết thúc

Liệt kê path, migration/contract revision, lệnh kiểm thử và kết quả quan sát,
rủi ro còn lại, rollback/forward recovery và bước tiếp theo. Không chuyển work
item thành `done` chỉ vì unit test pass.
