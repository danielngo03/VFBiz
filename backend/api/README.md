# VFBiz API Platform

NestJS 11 + Fastify modular monolith that owns VFBiz public APIs, identity and
business orchestration. This runtime is deliberately separate from the private
AI Platform.

## Architecture at a glance

```text
HTTP /api/v1
  -> presentation controller + DTO validation
  -> application use case + authorization policy
  -> domain model/policy
  -> infrastructure port (Prisma/provider/AI client)
  -> PostgreSQL + transactional outbox
```

`src/platform` contains cross-cutting technical capabilities. `src/modules`
contains business contexts with current or isolated experimental code. Runtime
foundation hiện chỉ compose `access`, `customer` và `product`; `engagement` và
`mobility` chưa public cho tới khi có approved implementation/release work.
Small features do not create new top-level modules.

## Local setup

Run these commands from the repository root:

```bash
cp backend/api/.env.example backend/api/.env
npm install
npm run prisma:generate --workspace @vfbiz/api
npm run start:dev --workspace @vfbiz/api
```

In local development the interactive API docs are enabled by default:

- Swagger UI: `http://127.0.0.1:8000/api-docs`
- Customer Scalar: `http://127.0.0.1:8000/reference/customer`
- Workforce Scalar: `http://127.0.0.1:8000/reference/workforce`
- Customer OpenAPI JSON: `http://127.0.0.1:8000/api-docs/customer/openapi.json`
- Workforce OpenAPI YAML: `http://127.0.0.1:8000/api-docs/workforce/openapi.yaml`

`/reference` chỉ redirect tới Customer Scalar để tương thích; không mount
Scalar tại một prefix cha vì middleware đó sẽ bắt cả `/reference/workforce`.

Set `VFBIZ_API_DOCS_ENABLED=false` to disable them locally. Staging and
production default to disabled unless an operator explicitly enables the docs
surface for a controlled environment.

Never commit `.env`. Chatbot, AI transport, Google Maps và Trip Planner chưa
được compose trong API foundation hiện tại, vì vậy không đặt các secret đó vào
API `.env`. Mỗi capability chỉ bổ sung configuration khi runtime và failure
policy tương ứng đã được duyệt.

Customer và workforce OIDC phải cấu hình issuer, JWKS URI, audience và
authorized-party allowlist riêng. Browser token nằm trong BFF server session,
không lưu ở `localStorage`; resource API chỉ nhận Bearer access token từ BFF
hoặc mobile client được phê duyệt.

Local-first mặc định dùng service host trên máy:

- API: `127.0.0.1:8000`
- PostgreSQL 17 + PostGIS: `127.0.0.1:5434`, database `vfbiz`
- Redis: `127.0.0.1:6379`, logical database `1`
- AI Platform: `127.0.0.1:8888`

Docker chỉ cần dùng khi muốn chạy một dependency chưa cài trên máy hoặc cần
replay môi trường tích hợp giống CI.

## Database workflow

```bash
npm run db:local:bootstrap --workspace @vfbiz/api
npm run db:local:check --workspace @vfbiz/api
npm run prisma:format --workspace @vfbiz/api
npm run prisma:validate --workspace @vfbiz/api
npm run prisma:migrate:dev --workspace @vfbiz/api -- --name <change>
# deployment only
npm run prisma:migrate:deploy --workspace @vfbiz/api
```

Native-local baseline:

- PostgreSQL `17.x` from `/opt/homebrew/opt/postgresql@17`.
- PostGIS `3.6.x`.
- Dedicated VFBiz listener at `127.0.0.1:5434`; PostgreSQL 14 on `5432`
  remains untouched.
- Bootstrap is idempotent and never drops a database or changes an existing
  role password. Override `VFBIZ_POSTGRES_*` only in the local shell.

If a migration fails on a newly created, empty local `vfbiz` database, inspect
the Prisma error first. Recreate that database only after confirming it has no
user data; never use this recovery procedure for shared or production data.

Migration creation must use an isolated developer database and requires review
of generated SQL. Do not edit a migration already merged or applied.

The ownership and migration rules are documented in
[data-model.md](docs/data-model.md).

## Read next

- Agent boundaries and verification commands: [AGENTS.md](AGENTS.md).
- Dependency and contract boundaries: [architecture.md](docs/architecture.md).
- Identity, profile, consent, session và DSAR:
  [identity-and-account.md](docs/identity-and-account.md).
- Vehicle Catalog, Customer Garage và Ownership boundary:
  [vehicle-catalog-and-garage.md](docs/vehicle-catalog-and-garage.md).
- Provider adapter, webhook and reconciliation policy:
  [integration-adapters.md](docs/integration-adapters.md).
- Conversation state, concurrency and handoff:
  [conversation-runtime.md](docs/conversation-runtime.md).
- Signed AI gateway, Vision and read-only tools:
  [ai-gateway-and-tools.md](docs/ai-gateway-and-tools.md).

Current implementation state and observed evidence belong in the active Git
work item, not in this onboarding document.
