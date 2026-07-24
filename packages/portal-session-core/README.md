# Portal Session Core

Server-only primitives shared by Customer Portal and Workforce Portal:

- versioned AES-256-GCM envelopes with key rotation;
- opaque session identifiers and CSRF tokens;
- Redis optimistic concurrency, subject/provider fences and leases;
- single-use OIDC attempts and replay-safe back-channel claims;
- private, non-cacheable HTTP responses.

Realm, audience, MFA, cookies, UI and business authorization remain owned by
each portal.
