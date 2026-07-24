# Product context instructions

## Ownership

Own structured Vehicle Catalog identities, immutable revisions, atomic releases
and public catalog projection. Drupal owns localized marketing copy/SEO/media;
Mobility owns energy-planning profiles; Customer owns Garage.

## Invariants

- Public reads use exactly one active release for the requested market.
- Release must be approved, effective and fresh; otherwise fail closed.
- Stable model/variant identity is never replaced by a source-system ID.
- Typed facts use explicit units/nullability. Never expose `extensionData`.
- Price/promotion requires its own source, validity and anomaly gate.
- Do not join revisions from different catalog releases.

## Read only when triggered

- Catalog/release/schema: `backend/api/docs/vehicle-catalog-and-garage.md`
- Persistence/migration: `backend/api/docs/data-model.md`
- Cross-system ownership: `docs/architecture/identity-customer-vehicle-foundation.md`

## Verify

Run focused product tests. Schema/contract/release changes additionally require
migration replay, API gate, contract lint, SDK generation and governance gate.
