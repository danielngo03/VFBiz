# VFBiz API Platform instructions

## Mission and authority
This NestJS application is the only owner of public `/api/v1`, customer and
workforce authorization, business transactions, idempotency, outbox and external
integration orchestration. It may call AI internally; it never delegates
authorization or side effects to the model.

## Capability boundaries

`access`, `customer` and `product` are currently composed business runtime
modules. `engagement` and `mobility` contain isolated experimental code but are
not loaded by `AppModule` until their own implementation/release work is
approved. Future boundaries remain in product/data docs until code exists.

Do not create a module for a screen, endpoint, vendor or small feature. Extend
the owning context. Do not scaffold an empty context: materialize it only with
an approved consumer/use case and tests. A new boundary requires a root ADR.

## Dependency rules

- Presentation calls application use cases; infrastructure implements
  application/domain ports. Domain code never imports NestJS, Fastify, Prisma
  or a provider SDK.
- Controllers never query Prisma or call vendor SDKs directly.
- Another context uses an exported application port, versioned contract or
  outbox event, never a deep import.
- Create a layer or folder only when code in that layer exists. The canonical
  vertical-slice layout is in the local `evolve-backend-capability` skill.

## HTTP and security

- Protected is the default; only `@Public()` routes bypass authentication.
- URI versioning is `/api/v1`; v1 changes are additive.
- Errors use RFC Problem Details and correlation ID.
- Mutations require object authorization and, where replay matters,
  `Idempotency-Key`.
- Never trust subject, realm, role or scope from an unsigned client header.

## Persistence

- Prisma schema is split by durable context under `prisma/models`.
- Migrations are immutable after merge; production uses `migrate deploy`.
- Consent and audit are append-only. Mutable projections carry source revision
  and freshness.
- Raw database access is confined to `platform/database` or a context's
  `infrastructure/persistence`.

## Read when needed

- Boundary/dependency rules: `docs/architecture.md`.
- Data/migration safety: `docs/data-model.md`.
- Identity, profile, consent, session và DSAR: `docs/identity-and-account.md`.
- Vehicle Catalog, Garage, ownership và VIN: `docs/vehicle-catalog-and-garage.md`.
- Provider adapters, webhooks and reconciliation: `docs/integration-adapters.md`.
- Conversation, handoff and concurrency: `docs/conversation-runtime.md`.
- Signed AI gateway, Vision upload and tools: `docs/ai-gateway-and-tools.md`.
- New vertical slice: local skill `evolve-backend-capability`.

## Commands

Use focused tests for bounded work. Controlled work runs the applicable full
gate from the repository root:

```bash
npm run lint --workspace @vfbiz/api
npm run typecheck --workspace @vfbiz/api
npm test --workspace @vfbiz/api -- --runInBand
npm run test:e2e --workspace @vfbiz/api -- --runInBand
npm run test:migrations --workspace @vfbiz/api
npm run prisma:validate --workspace @vfbiz/api
npm run prisma:generate --workspace @vfbiz/api
npm run build --workspace @vfbiz/api
```

When the public contract changes, also export OpenAPI, run root contract lint and
regenerate the shared SDK. Never report a gate that was not observed.
