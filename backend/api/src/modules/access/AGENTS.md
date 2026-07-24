# Access boundary

## Ownership

- CIAM owns credentials, MFA and authoritative provider-session revocation.
- API owns the customer session projection, local deny decision, revocation
  intent, retry/manual-review state and audit-safe response.
- A local revoke is fail-closed immediately even while CIAM reconciliation is
  pending or unavailable.

## Invariants

- Scope every read and mutation by verified issuer, subject, realm and client.
- Store only a local session fingerprint and an opaque secret-store reference.
  Never persist or log a raw token, cookie, provider handle, MFA secret or IP.
- A revoked or expired projection cannot be reactivated.
- Accept provider observations only from the trusted route and only when their
  monotonic revision is newer.
- Duplicate revoke requests must not dispatch duplicate CIAM calls.
- Disabled CIAM means durable manual review, never successful reconciliation.

## Read and verify

- Read `backend/api/docs/identity-and-account.md` for authority and lifecycle.
- Read `backend/api/docs/data-model.md` for migration and retention rules.
- Run focused unit/E2E tests plus the disposable PostgreSQL migration suite.
