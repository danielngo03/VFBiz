# Customer context instructions

## Ownership

Own Customer Profile, communication preferences, append-only consent, DSAR
workflow and Customer Garage. CIAM owns credentials/MFA; Product owns Vehicle
Catalog; Ownership owns verified vehicle associations.

## Invariants

- Derive customer only from verified `AccessPrincipal`; never accept customer ID
  or consent source from request data.
- Every query is subject-scoped. Customer routes require realm `customer`.
- Profile writes use ETag/OCC. Consent is append-only and replay-safe.
- DSAR records are workflow metadata, never proof that deletion/export finished.
- Do not store token, cookie, password, raw contact, VIN or private artifact URL.
- Garage entry is self-reported and never grants verified ownership.

## Read only when triggered

- Identity/Profile/Consent/DSAR: `backend/api/docs/identity-and-account.md`
- Garage/Ownership: `backend/api/docs/vehicle-catalog-and-garage.md`
- Schema/migration: `backend/api/docs/data-model.md`

## Verify

Run focused unit/E2E tests while editing. Auth, PII, contract or migration work
must also run `npm run verify:api`, migration replay, contract lint and the
governance gate required by the active work item.
