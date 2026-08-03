---
id: VFBIZ-0216
title: Bootstrap private AI database credentials without plaintext exposure
status: active
mode: controlled
priority: P0
owner_team: ai-platform-foundation
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
  - infra
  - root
allowed_paths:
  - backend/ai/scripts/prepare_cloud_sql_bootstrap_credential.py
  - backend/ai/tests/unit/platform/test_prepare_cloud_sql_bootstrap_credential.py
  - backend/ai/ops/gcp-database-bootstrap
  - infra/gcp
  - docs/work/items/VFBIZ-0199.md
  - docs/work/items/VFBIZ-0216.md
  - docs/work/plans/vivi-gcp-ai-platform.md
  - WORK.md
depends_on:
  - VFBIZ-0199
controlled_signals:
  - cloud-infrastructure
  - credential
  - database-migration
  - pii
exclusive_resources:
  - gcp-vinfast-development
  - terraform-state
  - database-migration
required_checks:
  - npm run verify:ai
  - npm run verify:ai:integration
  - npm run governance:check
revision: 2
review_date: "2026-08-31"
updated_at: "2026-08-02T11:40:00+07:00"
---

# Outcome

Bootstrap the private development AI database through a digest-pinned one-shot
Cloud Run Job without exposing administrator or workload database credentials
in shell arguments, `.env`, Git, state, logs or evidence.

## Constraints

- Use ADC/workload identity and Google APIs; never create a service-account key.
- The administrator password and database URL exist only in process memory and
  an exact numeric Secret Manager version.
- Every Cloud SQL, database, secret, bucket, project and region identity is
  verified before the first mutation.
- Provider ambiguity is reconciled; no blind retry may create an unknown active
  password or secret version.
- The bootstrap job is manual, has zero automatic retries and no scheduler.
- Public IP, public IAM, real corpus upload, OCR dispatch, dataset/model release,
  tuning and Chat activation remain out of scope.
- Development authority does not become Data, Privacy, Product, Brand, Legal or
  Release approval.

## Done when

- A dry-run-by-default operator prepares the initial PostgreSQL administrator
  credential through Cloud SQL Admin API and Secret Manager without placing the
  secret in a subprocess argument, file, log or return object.
- The operator verifies a private `POSTGRES_17` instance, expected database,
  Singapore-only secret replication, empty initial secret history and one
  create-only content-free GCS witness.
- Ambiguous Cloud SQL operation and Secret Manager version creation paths have
  deterministic reconciliation tests.
- A non-root, digest-pinned bootstrap image has SBOM and vulnerability evidence
  with zero unresolved Critical/High findings before private publication.
- A reviewed saved plan creates only the bootstrap identity, narrow IAM and
  manual Cloud Run Job; it changes or destroys no existing resource and creates
  no public principal, scheduler or secret payload.
- One exact job execution upgrades through Alembic head, reserves the immutable
  bootstrap epoch, creates two restricted login roles and publishes two
  different numeric runtime secret versions.
- The administrator secret version is disabled after successful verification;
  the job cannot be automatically re-executed and worker/reconciler dispatch
  remains disabled.
- Focused security tests, full AI checks, clean PostgreSQL integration, IaC
  validation/post-apply plan and independent correctness/risk reviews pass.

## Checkpoint

- VFBIZ-0199 revision 23 created the private PostgreSQL foundation exactly from
  reviewed saved plan digest
  `9bb0f86fe93f1882ea0a875b31df3295a06d166af1eaf735495ca528d0bfe04f`:
  13 added, zero changed and zero destroyed.
- Live instance `vfbiz-ai-postgres-dev` is `RUNNABLE`, private-only,
  `POSTGRES_17`, `db-f1-micro`, Zonal, 20 GiB, deletion-protected and
  `ENCRYPTED_ONLY`. Database `vfbiz_ai` exists.
- Administrator, submitter and reconciler Secret Manager containers exist with
  one user-managed replica in `asia-southeast1`; all contain zero versions.
- Post-apply plan digest
  `878381f284660f5f4558db53b9baca5ae65dcd5346b1198eee11431fd2b2bb4b`
  reports `No changes`. Cloud Run has zero services/jobs and Pub/Sub push is
  disabled.
- Commit `415316b` adds the dry-run-by-default ADC operator and 34 focused
  tests. The operator verifies exact database identity, private-only Cloud SQL,
  Singapore Secret Manager replication, empty history including destroyed
  versions, and the evidence bucket project/location/UBLA/PAP/retention and
  versioning policy before mutation. Live dry-run completed with
  `applied=false`; no password, secret version or witness was created.
- `npm run verify:ai` passed with 944 tests, 112 expected profile skips and one
  existing TestClient/httpx compatibility warning. Ruff and script Pyright are
  green. Provider 408/409/412/425/429/5xx responses are classified as ambiguous;
  Secret Manager creation is never blindly retried and indeterminate state is
  explicitly marked `do not rerun`.
- Two independent review/fix cycles closed secret-history replay, mutation HTTP
  classification, eventual-consistency retry, exact bucket/database preflight
  and error-chain exposure. Final reviews still reject `--apply`: the supplied
  authority digest and ambient ADC identity are not bound to an immutable named
  operator decision, and two consecutive unknown Cloud SQL password outcomes
  can leave the in-memory value unrecoverable.
- Review/fix for those causes is exhausted. No third silent patch or cloud
  mutation is permitted. Exact next action: create an external, create-only
  authority packet that pins work item/action/project/resources/expiry,
  designated least-privilege service-account identity, active exclusive claim
  and the reviewed foundation/post-apply plan digests; then design a separate
  recoverable credential escrow/reconciliation protocol for repeated Cloud SQL
  ambiguity before a newly authorized delivery lane may run `--apply`.

## Evidence

- [x] Exact private foundation and clean post-apply plan.
- [x] Independent foundation risk recommendation.
- [x] Dry-run administrator credential operator and bounded ambiguity tests.
- [ ] Immutable named-operator authority, least-privilege ADC and repeated
  Cloud SQL ambiguity recovery evidence for `--apply`.
- [ ] Bootstrap image supply-chain evidence and private digest.
- [ ] Create-only bootstrap-job plan and post-apply clean plan.
- [ ] One-shot execution, restricted role verification and administrator-secret
  disable evidence.
- [x] Two independent correctness/risk review cycles; final disposition rejects
  `--apply` until the recorded external gates are satisfied.
