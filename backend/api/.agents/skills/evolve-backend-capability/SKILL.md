---
name: evolve-backend-capability
description: Use when a VFBiz backend/API change adds or changes a NestJS business capability, Prisma schema or migration, public OpenAPI contract, persistence adapter, or cross-layer domain implementation.
---

# Evolve a backend capability

## Preconditions

1. Require an active Git work item with acceptance, owning bounded context,
   allowed paths and base revision. A claim is required only for delegated,
   controlled or parallel writing.
2. Acquire exclusive leases for every migration, public contract or lockfile in
   scope. If authority or a lease is missing, return `needs-decision` or
   `failed-safely`; do not create placeholder code.
3. Run the context resolver and load only the returned headings. Use
   `references/capability-template.md` for a new vertical slice,
   `docs/data-model.md` for persistence, and `docs/integration-adapters.md` for
   provider or webhook work.

## Workflow

1. Put the capability in an existing bounded context unless it has distinct
   vocabulary, data ownership, lifecycle and interface.
2. Classify the data and contract impact before choosing fields or framework
   types. Declare authorization, source/freshness, retention, idempotency,
   transaction/outbox and failure behavior.
3. Decide whether the public contract is unchanged, additive or breaking.
   Breaking `v1` changes require a versioning decision and architect approval.
4. Write the failing domain, application, schema or contract test that proves
   the bounded outcome.
5. Implement domain entities, value objects, errors and application ports
   without NestJS, Prisma, Fastify or vendor imports.
6. Implement the application use case and transaction boundary, followed by
   infrastructure adapters and HTTP presentation.
7. Add Prisma schema and a new reviewed migration when required. Never edit an
   applied migration; use expand → migrate/backfill → contract when
   compatibility needs multiple releases.
8. Export OpenAPI from NestJS, run compatibility checks and regenerate the
   shared SDK when the public contract changes.

## Evidence and exit

Run Prisma format/validate/generate, lint, typecheck, unit, PostgreSQL
integration, contract, negative-authorization, E2E and build checks that match
the change. Review migration SQL for destructive statements and PII. Report
changed paths, contract/migration revisions, observed checks, residual risk and
next action; then release every lease. Unit tests do not authorize staging,
production, merge or work-item completion.
