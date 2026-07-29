---
id: VFBIZ-0186
title: Enforce atomic dataset release provenance at PostgreSQL boundary
status: review
mode: controlled
priority: P0
owner_team: ai-platform-foundation
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/migrations/versions/20260729_0018_enforce_dataset_release_provenance.py
  - backend/ai/tests/integration/platform/test_dataset_release_provenance_migration.py
depends_on: []
controlled_signals:
  - ai-dataset
  - data-governance
  - migration
exclusive_resources:
  - database-migration
  - ai-dataset-registry
required_checks:
  - >-
    VFBIZ_RUN_DB_INTEGRATION=1 uv run --directory backend/ai pytest
    tests/integration/platform/test_dataset_release_provenance_migration.py -q
  - uv run --directory backend/ai alembic upgrade head --sql
revision: 4
review_date: "2026-08-29"
updated_at: "2026-07-29T06:52:09.541Z"
---

# Outcome

Make Dataset Registry provenance a non-bypassable PostgreSQL invariant for
approved/released dataset rows and active release pointers.

## Constraints

- This migration does not create or impersonate human approval.
- Promotion still requires the external approval registry and application gate.
- Existing candidate/draft rows remain compatible.
- Source/fetch revocation must rollback or tombstone dependent releases first.

## Done when

- Approved/released rows atomically lock and validate exact source revision,
  approved use, scan-passed digest and immutable scan evidence.
- Release pointer rejects non-released or digest-mismatched releases.
- Referenced source/fetch evidence cannot be tombstoned/deleted before release rollback.
- PostgreSQL integration proves valid promotion and all fail-closed paths.
- Upgrade and downgrade SQL are deterministic and reviewed.

## Checkpoint

- Implemented transaction-level release, pointer and evidence guards.
- Existing governed rows are revalidated atomically during upgrade.
- Downgrade refuses while governed releases or pointers remain.
- Production source/fetch transitions use bounded-retry SERIALIZABLE
  transactions, matching the PostgreSQL authority boundary.
- Canonical use, JSON shape and all authority-bearing source/fetch fields are
  fail-closed and immutable while a governed release depends on them.
- Exact next action: independent P0/P1 review, then full AI verification and
  checkpoint.

## Evidence

- [x] `VFBIZ_RUN_DB_INTEGRATION=1 uv run --directory backend/ai pytest tests/integration/platform/test_dataset_release_provenance_migration.py -q`
  — 2 passed, including populated downgrade refusal, upgrade rejection for
  invalid legacy provenance, evidence immutability and active-pointer fencing.
- [x] `VFBIZ_RUN_DB_INTEGRATION=1 uv run --directory backend/ai pytest tests/integration/platform/test_dataset_release_provenance_migration.py tests/integration/datasets/test_postgres_dataset_registry.py -q`
  — 5 passed; production registry transitions and migration authority agree.
- [x] `uv run --directory backend/ai alembic upgrade head --sql`
  — deterministic offline SQL generated successfully.
- [x] `uv run --directory backend/ai ruff check ...`
  — passed.
- [x] `uv run --directory backend/ai pyright ...`
  — 0 errors.

### review — 2026-07-29T06:52:09.541Z

Independent reviewer-verifier approved with no remaining P0/P1 after three evidence-driven review rounds; full AI and PostgreSQL integration gates passed.
