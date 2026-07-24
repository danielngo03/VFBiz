# Portal session core instructions

Root `AGENTS.md` applies. This package is a controlled security boundary.

- Keep it provider- and portal-neutral. It must not know Customer, Workforce,
  Keycloak realm, capability or business policy.
- Store only encrypted token/session payloads; never log plaintext credentials.
- Session writes use optimistic concurrency. Revocation is local-deny-first.
- Cryptographic envelopes are versioned, key-identified and authenticated with
  record-specific AAD.
- Redis Lua changes require race, stale-writer and expiry tests.
- Public exports require a real consumer in both portals or a contract test.

Run `npm run typecheck` and `npm test` in this workspace for every change.
