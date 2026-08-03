---
id: VFBIZ-0219
title: Correct Cloud SQL credential polling permission contract
status: review
mode: controlled
priority: P0
owner_team: reliability-engineering
accountable_role: release-owner
primary_workspace: infra
affected_workspaces:
  - infra
  - root
allowed_paths:
  - infra/gcp/database_credential_operator.tf
  - infra/gcp/tests/database_credential_operator.tftest.hcl
  - infra/gcp/README.md
  - docs/work/items/VFBIZ-0219.md
  - docs/INDEX.md
  - docs/INDEX.json
  - WORK.md
depends_on:
  - VFBIZ-0217
  - VFBIZ-0218
controlled_signals:
  - cloud-infrastructure
  - iam
exclusive_resources:
  - gcp-vinfast-development
  - terraform-state
required_checks:
  - tofu -chdir=infra/gcp validate
  - tofu -chdir=infra/gcp test -filter=tests/database_credential_operator.tftest.hcl
  - npm run governance:check
revision: 2
review_date: "2026-08-31"
updated_at: "2026-08-02T13:08:00+07:00"
---

# Outcome

Make Cloud SQL credential operation polling rely on Google's documented
`cloudsql.instances.get` authorization while retaining the exact-instance IAM
condition and the minimum permission set needed for the one development
credential action.

## Constraints

- Remove the method-like `cloudsql.operations.get` string from the custom role.
- Retain exactly `cloudsql.databases.get`, `cloudsql.instances.get` and
  `cloudsql.users.update` under the existing condition for
  `vfbiz-ai-postgres-dev`.
- Do not add an unconditional polling binding, broaden the resource condition,
  grant a predefined administrative role or change another GCP resource.
- Regenerate only a default-off saved plan after the repository checks pass.
  Planning may read the existing development foundation but must not apply,
  mutate credentials or enable the operator.
- A live enabled polling canary remains a named-human Cloud Operator gate. A
  `403` must stop the lane; it must never trigger automatic IAM widening.

## Done when

- The native OpenTofu test proves the exact three-permission set and exact
  instance condition.
- Static verification proves no `cloudsql.operations.get`, project-wide user
  update, unconditional polling binding or administrative role remains.
- OpenTofu formatting, validation and the focused native test pass.
- A regenerated default-off saved plan has zero create, update, delete or
  replacement actions and its SHA-256 is recorded.
- Independent recommendation remains read-only and no cloud apply occurs.

## Checkpoint

- Commit `104b1df` retains exactly `cloudsql.databases.get`,
  `cloudsql.instances.get` and `cloudsql.users.update`; the exact instance
  condition is unchanged. OpenTofu validates and the native suite passes 4/4.
- Saved plan `infra/gcp/vfbiz-0219-default.tfplan` is private/ignored, mode
  `0600`, SHA-256
  `65eedad23f8e5a99cdb8a8634b1f0bf1852e4e97359ea6a25090377c04d7dae7`.
  It contains 53 resource and 26 output no-ops and no mutation action.
- Independent correctness and risk reviewers report no repository finding and
  close `VFBIZ0218-IAC-VERIFIER-PERMISSION-DRIFT` and
  `VFBIZ-0218/RISK/SQL-PERMISSION-CONTRACT-DIVERGENCE`.
- Exact next action: a named-human Cloud Operator may separately authorize an
  enabled condition canary after the remote authority broker exists. A 403 must
  stop; do not widen IAM or apply this plan.

## Evidence

- [x] Read-only Reliability recommendation and official permission mapping.
- [x] Exact three-permission IaC and native test.
- [x] Default-off zero-change saved plan and digest.
- [x] Independent correctness and risk recommendations.
- [ ] Live polling canary; remains human-gated and is not authorized here.
