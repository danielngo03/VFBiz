---
id: VFBIZ-0218
title: Enforce live claim authority for controlled GCP credential apply
status: active
mode: controlled
priority: P0
owner_team: agent-platform
accountable_role: release-owner
primary_workspace: root
affected_workspaces:
  - root
  - infra
allowed_paths:
  - tools/gcp-controlled-apply.mjs
  - tools/lib/gcp-controlled-apply.mjs
  - tests/governance/gcp-controlled-apply.test.mjs
  - package.json
  - infra/gcp/database_credential_operator.tf
  - infra/gcp/tests/database_credential_operator.tftest.hcl
  - infra/gcp/README.md
  - docs/work/items/VFBIZ-0218.md
  - docs/INDEX.md
  - docs/INDEX.json
  - WORK.md
depends_on:
  - VFBIZ-0216
  - VFBIZ-0217
controlled_signals:
  - authorization
  - cloud-infrastructure
  - credential
  - iam
exclusive_resources:
  - agent-control-state
  - gcp-vinfast-development
  - terraform-state
required_checks:
  - npm run verify:agent-runtime
  - tofu -chdir=infra/gcp validate
  - tofu -chdir=infra/gcp test -filter=tests/database_credential_operator.tftest.hcl
  - npm run governance:check
revision: 2
review_date: "2026-08-31"
updated_at: "2026-08-02T13:08:00+07:00"
---

# Outcome

Provide one fail-closed, keyless validation boundary for the reviewed
VFBIZ-0217 saved plan. It proves the current agent claim, fencing token,
exclusive leases, authority packets, saved-plan semantics, base revision and
exact Google identity, but remains ineligible to mutate cloud resources until a
remote signed authority broker and cloud-side bypass denial exist.

## Constraints

- The command is validation-only. `--execute`, the library authorization helper
  and apply-invocation builder all fail with `EXECUTE_BROKER_REQUIRED` before
  state or cloud access.
- It consumes an externally issued authority object; it cannot create, upload,
  modify or reinterpret Product, Risk, Release or Cloud Operator decisions.
- The active claim must belong to VFBIZ-0218, use the exact current fencing token,
  retain active `gcp-vinfast-development` and `terraform-state` leases, and pin
  the current Git revision and allowed plan digest.
- The packet must pin the VFBIZ-0217 action, project, project number, Singapore
  region, instance, database, secret, evidence bucket, operator principal,
  authority generation, foundation/post-apply plan digests and a validity window
  of no more than four hours.
- The Google access token and authority content stay in process memory. They may
  not enter shell arguments, Git, `.env`, logs, receipts or test fixtures.
- The exact ADC identity must equal the named packet principal. Project/identity
  ambiguity, unavailable token introspection, expired authority, dirty allowed
  paths or plan drift all fail before `tofu apply`.
- The plan verifier allows only the reviewed create-only credential authority
  resources and rejects update, delete, replace, public IAM, secret payload,
  Cloud SQL user, workload, scheduler or unrelated output mutation.
- Cloud SQL mutation remains instance-scoped. Operation polling uses the
  documented `cloudsql.instances.get` authorization path; an operation resource
  permission must not be placed behind an incompatible Instance-only condition.
- No cloud apply, credential mutation, public Chat activation, corpus upload,
  OCR dispatch, model evaluation or tuning is authorized by this work item.
- VFBIZ-0216 repeated-unknown credential recovery remains a separate stop gate.

## Done when

- Unit tests prove stale/released claims, stale fencing tokens, missing or expired
  leases, wrong base revision, wrong ADC subject, expired/mismatched packets and
  altered saved plans stop before the apply subprocess is constructed.
- The plan verifier rejects every action outside the exact allowlist and binds
  the plan SHA-256 to both the external packet and command input.
- The validator uses the canonical agent-control directory, a private
  content-identical plan snapshot, absolute trusted tool paths and a sanitized
  environment. Local execution remains impossible.
- Cloud SQL IAM tests prove project-wide user update is absent and operation
  polling does not depend on an unsupported operation resource condition.
- A live validation-only run records content-free identity, claim, lease, packet
  generation and plan digests. It performs no cloud mutation.
- OpenTofu, agent-runtime, governance and independent correctness/risk reviews
  pass. Reviewers remain recommendation-only.
- A future broker must verify signed issuer/recovery envelopes, broker-owned
  claim state and cloud IAM denial of direct apply before any execute path may
  be designed. Named-human acceptance remains necessary but is not sufficient.

## Checkpoint

- Commit `fb1218b` closes the local semantic allowlist, exact claim/revision,
  recovery-schema and saved-plan replacement findings. Eighteen focused tests,
  agent-runtime verification and governance are green. Every local execute path
  is unconditionally disabled and receipts record `execution_eligible=false`.
- VFBIZ-0219 commit `104b1df` removes the redundant
  `cloudsql.operations.get`, keeps the exact-instance condition and regenerates
  a default-off plan with SHA-256
  `65eedad23f8e5a99cdb8a8634b1f0bf1852e4e97359ea6a25090377c04d7dae7`:
  53 resource and 26 output no-ops, with no cloud mutation.
- Final review closes all original local correctness findings and the
  SQL-permission drift. It still rejects apply because decision/recovery issuer
  provenance, broker-owned authority state, direct-IAM bypass denial and live
  condition behavior are external evidence gaps.
- Exact next action: define a separate remote signed-authority broker work item
  with an allowlisted KMS issuer, separation-of-duties IAM, bounded payloads and
  direct-path denial tests. Do not reopen a third local fix/review cycle.

## Evidence

- [x] VFBIZ-0217 default-off saved plan and two final review recommendations.
- [x] Live claim/lease/fencing and exact ADC identity verifier.
- [x] Digest-bound create-only saved-plan semantic verifier.
- [x] Instance-scoped Cloud SQL permission contract and compatible polling
  authorization mapping.
- [ ] Live validation-only, content-free receipt.
- [x] Two independent local correctness and risk review cycles.
- [ ] KMS-signed independent issuer, broker-owned state and cloud-side direct
  apply denial; no execute path or apply is currently authorized.
- [ ] Named-human live polling canary and validation receipt.
