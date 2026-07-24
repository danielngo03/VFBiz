---
id: plan-vfbiz-0004
title: NestJS API Platform rebuild plan
status: archived
owner_role: engineering-lead
scope: api
when_to_read:
  - api-rebuild
tags:
  - plan
  - nestjs
  - api
revision: 1
review_date: 2026-07-22
supersedes: []
---

# NestJS API Platform Rebuild Implementation Plan

Use the current work item and nearest workspace instructions. This historical
plan does not authorize implementation by itself.

**Goal:** Replace `backend/api` with a clean NestJS 11/Fastify modular monolith whose stable bounded contexts, Prisma schema, HTTP conventions and quality gates can support the VFBiz roadmap.

**Architecture:** Root remains the only monorepo. `backend/api` is one deployable Nest application; `src/platform` owns technical infrastructure and `src/modules` owns durable business contexts. Controllers and Prisma are adapters around framework-independent application/domain code.

**Tech Stack:** Node.js 20+, TypeScript 5.9, NestJS 11, Fastify 5, Prisma 7/PostgreSQL, class-validator, JOSE, Pino, OpenTelemetry, Jest.

## Global Constraints

- Preserve the old workspace in a timestamped Git-ignored backup before replacement.
- Top-level modules are exactly `access`, `customer`, `product`, `mobility`, `sales`, `ownership`, `commerce`, `engagement`, `operations`.
- Vendor names never appear as top-level modules.
- Domain code cannot import NestJS, Fastify, Prisma or provider SDKs.
- Public endpoints are explicit; protected is the default.
- API URI prefix is `/api/v1`; internal operational HTTP is not public by default.
- Prisma migration SQL remains versioned; production uses `prisma migrate deploy`.
- Never commit `.env`, credentials, PII, production data or provider responses.

---

## File map

```text
backend/api/
├── prisma/{schema.prisma,models/,migrations/,seed/}
├── src/
│   ├── main.ts
│   ├── app.module.ts
│   ├── platform/{config,http,security,database,idempotency,outbox,audit,observability,health}/
│   └── modules/{access,customer,product,mobility,sales,ownership,commerce,engagement,operations}/
├── test/{unit,integration,contract,e2e,architecture}/
├── .env.example
├── nest-cli.json
├── package.json
├── tsconfig.json
└── tsconfig.build.json
```

### Task 1: Recoverable replacement and official Nest scaffold

**Files:**
- Backup: `local-data/backend-rebuild/<timestamp>/api/`
- Replace: `backend/api/**`
- Create: `backend/api/README.md`

**Interfaces:**
- Consumes: approved design `docs/superpowers/specs/2026-07-22-backend-platform-rebuild-design.md`.
- Produces: official Nest CLI application recognized by root npm workspace.

- [ ] **Step 1: Record and verify the backup manifest**

Create SHA-256 manifest for all current files and copy the directory into the ignored backup. Verify a sample and the manifest before replacement.

Run:

```bash
test -d backend/api
git check-ignore local-data
find backend/api -type f -print0 | sort -z | xargs -0 shasum -a 256 > /tmp/vfbiz-api-before.sha256
```

Expected: manifest is non-empty and contains `backend/api/package.json`.

- [ ] **Step 2: Move the old directory to the backup and scaffold Nest**

Use `nest new` with npm, strict TypeScript and no Git repository. Move the generated application to `backend/api`; do not manually invent CLI metadata.

Run:

```bash
npx @nestjs/cli@11.0.24 new api --package-manager npm --strict --skip-git --directory /tmp/vfbiz-nest-api
```

Expected: `/tmp/vfbiz-nest-api/nest-cli.json`, `src/main.ts` and `src/app.module.ts` exist.
Set the generated package name to `@vfbiz/api` before root workspace installation.

- [ ] **Step 3: Verify root workspace discovery**

Run:

```bash
npm install
npm exec --workspace @vfbiz/api nest info
```

Expected: Nest 11, TypeScript and Node versions are printed without resolution errors.

- [ ] **Step 4: Commit the clean scaffold checkpoint**

```bash
git add backend/api package.json package-lock.json
git commit -m "build(api): reinitialize NestJS application"
```

### Task 2: Dependency and configuration foundation

**Files:**
- Modify: `backend/api/package.json`
- Create: `backend/api/.env.example`
- Create: `backend/api/src/platform/config/env.schema.ts`
- Create: `backend/api/src/platform/config/configuration.ts`
- Create: `backend/api/src/platform/config/config.module.ts`
- Test: `backend/api/test/unit/platform/config/env.schema.spec.ts`

**Interfaces:**
- Produces: `validateEnvironment(input): EnvironmentVariables` and typed configuration namespaces.

- [ ] **Step 1: Install only approved baseline dependencies**

Install Nest Config/Swagger/Terminus/Throttler, Fastify helmet/compress, Prisma 7, JOSE, Pino, validation, Joi and OpenTelemetry. Do not install CQRS, Kafka, BullMQ, LangChain or a model SDK.

- [ ] **Step 2: Write failing environment validation tests**

Cover: valid development config, invalid port, missing database URL, live Maps without server key, production AI URL outside private network and unknown provider mode.

```ts
expect(() => validateEnvironment({NODE_ENV: 'production'})).toThrow();
expect(validateEnvironment(validDevelopment).HTTP_PORT).toBe(3000);
```

- [ ] **Step 3: Implement startup validation**

`EnvironmentVariables` must include app/HTTP/database/Redis/OIDC/Maps/AI/telemetry values. `ConfigModule.forRoot` must use `validateEnvironment`, `cache: true`, `expandVariables: false` and `.env` only outside production.

- [ ] **Step 4: Run focused checks**

```bash
npm test --workspace @vfbiz/api -- env.schema.spec.ts
npm run typecheck --workspace @vfbiz/api
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add backend/api package-lock.json
git commit -m "feat(api): add validated runtime configuration"
```

### Task 3: HTTP platform and API convention

**Files:**
- Modify: `backend/api/src/main.ts`
- Modify: `backend/api/src/app.module.ts`
- Create: `backend/api/src/platform/http/http.module.ts`
- Create: `backend/api/src/platform/http/problem-details.filter.ts`
- Create: `backend/api/src/platform/http/correlation.interceptor.ts`
- Create: `backend/api/src/platform/http/public.decorator.ts`
- Create: `backend/api/src/platform/http/request-context.ts`
- Test: `backend/api/test/e2e/platform/http-platform.e2e-spec.ts`

**Interfaces:**
- Produces: URI versioning, global `ValidationPipe`, RFC Problem Details, correlation ID and explicit public metadata.

- [ ] **Step 1: Write failing E2E assertions**

Assert `/api/v1/health/live` works, unversioned route is 404, invalid DTO is RFC Problem Details and caller correlation ID is returned only after validation.

- [ ] **Step 2: Implement Fastify bootstrap**

Create `NestFastifyApplication`, register Helmet/compression, set prefix `api`, enable URI versioning with default `1`, install strict validation (`whitelist`, `forbidNonWhitelisted`, `transform`) and close on signals.

- [ ] **Step 3: Implement stable error and request metadata**

Problem response fields are `type`, `title`, `status`, `detail`, `instance`, `code`, `correlationId`. Never include stack trace, request body, authorization or cookie.

- [ ] **Step 4: Verify and commit**

```bash
npm run test:e2e --workspace @vfbiz/api -- http-platform.e2e-spec.ts
npm run build --workspace @vfbiz/api
git add backend/api package-lock.json
git commit -m "feat(api): establish HTTP platform conventions"
```

### Task 4: Prisma database platform and declarative schema

**Files:**
- Create: `backend/api/prisma.config.ts`
- Create: `backend/api/prisma/schema.prisma`
- Create: `backend/api/prisma/models/platform.prisma`
- Create: `backend/api/prisma/models/access.prisma`
- Create: `backend/api/prisma/models/customer.prisma`
- Create: `backend/api/prisma/models/product.prisma`
- Create: `backend/api/prisma/models/mobility.prisma`
- Create: remaining bounded-context `.prisma` files from the approved map.
- Create: `backend/api/src/platform/database/prisma.service.ts`
- Create: `backend/api/src/platform/database/database.module.ts`
- Test: `backend/api/test/architecture/prisma-schema.spec.ts`

**Interfaces:**
- Produces: `PrismaService`, `DatabaseModule`, validated multi-file schema and initial migration.

- [ ] **Step 1: Write schema architecture test**

Assert every approved bounded context has one schema file, datasource/generator exist only in `schema.prisma`, and raw database access does not occur outside `platform/database` or a module `infrastructure/persistence` path.

- [ ] **Step 2: Define platform models**

Create UUID-based `IdempotencyRecord`, `OutboxEvent`, `AuditEvent` and `SourceRevision` with timestamps, correlation ID, status and indexes. Do not store secrets or raw provider payloads.

- [ ] **Step 3: Define initial domain projections**

Create minimal source-backed customer, product, mobility and engagement records needed by the approved staging scope. Every mutable projection has revision/freshness; consent and audit records are append-only.

- [ ] **Step 4: Generate and validate**

```bash
npx prisma format --config backend/api/prisma.config.ts
npx prisma validate --config backend/api/prisma.config.ts
npx prisma generate --config backend/api/prisma.config.ts
npm test --workspace @vfbiz/api -- prisma-schema.spec.ts
```

Expected: all commands pass.

- [ ] **Step 5: Create migration without applying to shared/staging DB**

Use an isolated local PostgreSQL database. Review generated SQL, then commit schema and migration history.

### Task 5: Stable bounded-context module graph

**Files:**
- Create: `backend/api/src/modules/<context>/<context>.module.ts` for all nine contexts.
- Create: `backend/api/src/modules/<context>/index.ts` for all nine contexts.
- Create: `backend/api/test/architecture/module-boundaries.spec.ts`
- Modify: `backend/api/src/app.module.ts`

**Interfaces:**
- Produces: Nest module graph with no cross-context deep imports.

- [ ] **Step 1: Write boundary tests before modules**

Test exact module names, forbid unapproved top-level module directories, forbid `common/models`, `common/services`, top-level vendor modules and deep imports into another context.

- [ ] **Step 2: Create minimal module classes**

Each context exports only its Nest module. Do not create empty `controller`, `service` or repository files merely to populate folders.

```ts
@Module({})
export class MobilityModule {}
```

- [ ] **Step 3: Compose modules and verify graph**

```bash
npm test --workspace @vfbiz/api -- module-boundaries.spec.ts
npm run build --workspace @vfbiz/api
```

- [ ] **Step 4: Commit**

```bash
git add backend/api
git commit -m "refactor(api): establish bounded context module graph"
```

### Task 6: Security, health and observability baseline

**Files:**
- Create security guards/decorators under `src/platform/security/`.
- Create health indicators under `src/platform/health/`.
- Create Pino and OpenTelemetry setup under `src/platform/observability/`.
- Test: `test/e2e/platform/security-default.e2e-spec.ts`.
- Test: `test/integration/platform/readiness.spec.ts`.

**Interfaces:**
- Produces: protected-by-default guard, explicit public routes, liveness/readiness distinction and redacted logs.

- [ ] **Step 1: Write negative security tests**

Missing authentication, malformed token, wrong issuer/audience, cookie/bearer ambiguity and missing object authorization must fail closed.

- [ ] **Step 2: Implement JOSE/JWKS port and guards**

The default adapter denies all. No header can directly assert subject, realm, role or permission.

- [ ] **Step 3: Implement liveness/readiness**

Liveness checks process only. Readiness requires database migration compatibility and mandatory adapters; it must not return ready from `SELECT 1` alone.

- [ ] **Step 4: Verify and commit**

```bash
npm run test:e2e --workspace @vfbiz/api
npm run test:integration --workspace @vfbiz/api
git add backend/api
git commit -m "feat(api): add security health and observability baseline"
```

### Task 7: OpenAPI, contract and delivery gate

**Files:**
- Create: `backend/api/src/platform/openapi/openapi.ts`
- Create: `backend/api/scripts/export-openapi.ts`
- Modify: root `contracts/openapi/public-v1.yaml` only through the exclusive contract lease.
- Create: `backend/api/test/contract/openapi.spec.ts`
- Update: `backend/api/README.md`, `backend/api/docs/architecture.md`.

**Interfaces:**
- Produces: reproducible public OpenAPI and generated-client compatibility evidence.

- [ ] **Step 1: Add contract tests**

Assert no undocumented public route, every operation has stable ID, auth/public metadata, Problem Details responses and version prefix.

- [ ] **Step 2: Export and lint OpenAPI**

```bash
npm run openapi:export --workspace @vfbiz/api
npm run contracts:lint
```

- [ ] **Step 3: Run full gate**

```bash
npm run lint --workspace @vfbiz/api
npm run typecheck --workspace @vfbiz/api
npm run test --workspace @vfbiz/api
npm run test:e2e --workspace @vfbiz/api
npm run build --workspace @vfbiz/api
npm audit --workspace @vfbiz/api --audit-level=high
```

Expected: zero failed test/build and zero high/critical advisory.

- [ ] **Step 4: Record work-item evidence and commit docs**

Move the API rebuild item to `review` only after observed output is attached. Do not mark it `done` until database integration and staging acceptance pass.
