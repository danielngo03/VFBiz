---
id: staging-mvp-boundaries
title: Staging MVP runtime boundaries
status: superseded
owner_role: architect
scope: cross-system
when_to_read:
  - staging-mvp
  - cross-system
  - controlled
tags:
  - architecture
  - boundaries
  - data
revision: 3
review_date: 2026-08-22
supersedes: []
---

# Staging MVP runtime boundaries

> Tài liệu lịch sử. Ranh giới active của Customer Chatbot nằm tại
> `docs/architecture/customer-chatbot-v6.md`.

## Surfaces and authority

- `drupal/`: public SSR, CMS, SEO, VI/EN content, widget and account/trip entry.
- `backend/api/`: only public `/api/v1`, caller/object authorization, customer,
  vehicle, trip, operations, audit, idempotency, and provider orchestration.
- `backend/ai/`: private policy, retrieval, ingestion, evaluation, provider and
  read-only tool proposal service; never public to a client.
- `apps/customer-portal/`: BFF-backed account, garage, chat and trip journeys.
- `apps/operations-admin/`: workforce RBAC/SoD, data/release and audit surfaces.
- Keycloak: credentials, MFA and identity verification; API stores only opaque
  subject references.

## Data stores

- API PostgreSQL/PostGIS: customer, consent, garage, vehicle/trip projections,
  idempotency, outbox and audit.
- AI PostgreSQL/pgvector: chunks, ACL metadata, embeddings, evaluations and
  release manifests.
- Keycloak PostgreSQL: identity state.
- Drupal MariaDB: editorial content/configuration.
- Redis: BFF/session references, cache, locks and rate limits.
- Object storage: source binaries and dataset artifacts; not Drupal.

## AI and trip rule

Trip calculation is deterministic. AI may explain a plan or propose the
`plan_ev_trip` tool, but API validates scope and executes it. Models do not own
live facts, authorization, calculations, or side effects.

## Exclusive integration resources

Public OpenAPI, database migrations, Drupal config sync, root lockfile, and AI
dataset/release registries have one writer lease at a time.
