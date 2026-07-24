# Local Keycloak staging foundation

This directory starts two isolated local realms for the Lane A identity work:

- `vfbiz-customer` for customer CIAM and the customer BFF;
- `vfbiz-workforce` for workforce SSO/MFA and the Workforce Portal BFF.

The realm imports intentionally contain no user, password, client secret, token,
email address or production endpoint. Keycloak creates confidential-client
credentials at import time; retrieve them interactively for local use and never
commit them.

## Start natively

VFBiz pins Keycloak `26.7.0`, verifies the official release artifact before it
is placed under ignored `local-data/`, and uses OpenJDK 25. After those
dependencies exist:

```bash
./infra/local/keycloak/native-start.sh
./infra/local/keycloak/native-reconcile.sh
./infra/local/keycloak/native-check.sh
./infra/local/keycloak/native-identity-bridge-smoke.sh
node ./infra/local/keycloak/sync-application-env.mjs
./infra/local/keycloak/native-stop.sh
```

The bootstrap script creates a dedicated `vfbiz_keycloak` database on native
PostgreSQL 17 at `127.0.0.1:5434`, generates local-only secrets under
`local-data/keycloak/native/.env`, and copies the reviewed realm imports into
the local distribution. Realm imports use those ignored local secrets; no
credential is stored in Git. The bootstrap never rewrites an existing password
or drops a database.

`sync-application-env.mjs` copies only the reviewed local client credentials
into ignored `backend/api/.env`, `apps/customer-portal/.env.local` and
`apps/workforce-portal/.env.local`, creates local token-vault encryption keys
when absent, applies file mode `0600` and never prints a secret.

`native-start.sh` invokes the idempotent reconciler because Keycloak does not
overwrite an existing realm on import. The reconciler ensures the Customer
Identity Bridge service account has only `view-users`/`manage-users`, plus the
reviewed legacy workforce release roles, Workforce Portal callback and built-in
OIDC AMR mapper; it never creates a human user. Business capabilities remain
API-owned and are not provisioned into Keycloak tokens. `native-check.sh` then
verifies discovery, JWKS, confidential-client PKCE, callback URIs, customer
scopes, bridge privileges, migration roles and AMR access-token mapping without
printing credentials. Customer BFF also configures signed OIDC back-channel
logout and five-minute access tokens with refresh-token rotation. Customer and
Workforce SSO/client idle and maximum lifetimes remain bounded independently.

## Optional Compose start

1. Copy `.env.example` to an untracked environment file.
2. Set `KEYCLOAK_IMAGE` to an explicitly reviewed image digest.
3. Set local-only bootstrap credentials in the environment.
4. Run `docker compose --env-file <local-file> up` from this directory.

The checked-in redirect URIs are loopback staging values only. Production realm,
SMTP, federation, conditional access and secret-manager integration require
separate approved infrastructure work.
