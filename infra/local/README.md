# Local staging dependencies

This Compose stack is optional. VFBiz development is local-first: prefer
PostgreSQL, Redis, API and AI services running directly on `127.0.0.1` when they
are available on the laptop. Use Compose only when a dependency is not installed
locally or an integration test specifically needs the containerized service.

Default local ports:

- API Platform: `127.0.0.1:8000`
- AI Platform: `127.0.0.1:8888`
- PostgreSQL 17 + PostGIS native: `127.0.0.1:5434`
- Redis: `127.0.0.1:6379`
- Keycloak: `127.0.0.1:8080`

The optional Compose network keeps its PostgreSQL port private and does not
publish it to the host. When used, this stack is a developer approximation, not
a production topology.
It starts PostGIS for API data, pgvector for AI data, a dedicated Keycloak
database, Keycloak 26.7.0 and Redis. MariaDB/Drupal remains in the Drupal
workspace.

1. Copy `.env.example` to `.env` and generate unique local secrets.
2. Review the realm definitions under `keycloak/`; they contain no user password
   or client secret.
3. Run `docker compose --env-file .env up -d`.
4. Apply API and AI migrations with their workspace commands.

All ports bind to loopback. Databases and Redis are private-network only. Image
tags are pinned for reproducible local staging but still require digest pinning,
SBOM and advisory review before a production ADR.
