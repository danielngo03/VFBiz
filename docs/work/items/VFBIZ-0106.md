---
id: VFBIZ-0106
title: Enforce AI PostgreSQL integration gate
status: done
mode: controlled
priority: P0
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - package.json
  - .github/workflows/foundation-quality.yml
  - docs/work/items/VFBIZ-0106.md
  - WORK.md
depends_on: []
controlled_signals:
  - migration
  - ai-release
exclusive_resources:
  - ci-workflow
required_checks:
  - npm run verify:ai:integration
  - npm run verify:ai
  - npm run governance:check
revision: 5
review_date: "2026-07-25"
updated_at: "2026-07-25T14:47:00.985Z"
---

# Outcome

AI PostgreSQL integration tests run against an isolated PostgreSQL 17/pgvector
database in CI and fail when the database or migrations are unavailable instead
of being silently skipped.

## Constraints

- The integration database must be isolated and disposable.
- CI credentials are job-local test credentials, never reusable secrets.
- Unit verification may remain database-independent, but the required
  integration command must reject a missing opt-in or database URL.
- Tests must not target the developer or staging database by accident.

## Done when

- A dedicated command enables the four PostgreSQL integration suites and
  explicitly targets an isolated database.
- GitHub Actions provisions PostgreSQL 17 with pgvector, migrates it, and runs
  the non-skipping command.
- The command rejects an absent database configuration rather than silently
  reporting success.
- Existing AI verification remains green.

## Checkpoint

- Exact next action: add a fail-closed integration runner and CI PostgreSQL
  service, then prove it against a fresh local test database.

## Evidence

- [x] `npm run verify:ai:integration` — migrations 0001–0008 and 17 PostgreSQL
  integration tests passed against isolated PostgreSQL 17.10 + pgvector on
  2026-07-25; the disposable database was removed afterward.
- [x] `npm run verify:ai` — Ruff, Pyright, 191 unit/contract tests and Alembic
  static migration validation passed on 2026-07-25.
- [x] `npm run governance:check` — docs, reports, guides, authorization, work
  schemas and 61 provider-neutral scenarios passed on 2026-07-25.

### review — 2026-07-25T14:47:00.855Z

Fail-closed CI command and PostgreSQL 17/pgvector service verified locally.

### done — 2026-07-25T14:47:00.985Z

AI PostgreSQL integration tests are now a required independent CI job.
