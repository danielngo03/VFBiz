---
id: VFBIZ-0217
title: Bind Cloud SQL credential bootstrap to immutable GCP authority
status: active
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
  - infra/gcp/variables.tf
  - infra/gcp/outputs.tf
  - infra/gcp/terraform.tfvars.example
  - infra/gcp/README.md
  - infra/gcp/tests/database_credential_operator.tftest.hcl
  - docs/work/items/VFBIZ-0217.md
  - WORK.md
depends_on:
  - VFBIZ-0199
  - VFBIZ-0216
controlled_signals:
  - cloud-infrastructure
  - iam
  - credential
exclusive_resources:
  - gcp-vinfast-development
  - terraform-state
required_checks:
  - tofu -chdir=infra/gcp fmt -check
  - tofu -chdir=infra/gcp validate
  - npm run governance:check
revision: 3
review_date: "2026-08-31"
updated_at: "2026-08-02T12:24:00+07:00"
---

# Outcome

Represent a default-off, keyless and least-privilege GCP authority boundary for
the one-time Cloud SQL administrator credential bootstrap. The IaC observes an
externally issued, create-only authority object by exact SHA-256 and generation;
it never issues human authority, creates a credential payload or runs the
bootstrap operator.

## Constraints

- Project is exactly `vinfast-503003` (`81588547131`) in
  `asia-southeast1`; the accepted foundation and post-apply plan digests remain
  pinned to VFBIZ-0199 revision 23.
- Keep `database_credential_operator_enabled=false` by default. Enabling it may
  create only one dedicated service account, narrow custom roles/bindings and
  one expiring impersonation grant.
- The authority object must pre-exist in the evidence bucket and be pinned by
  canonical digest, exact object name and positive generation. Terraform is not
  the issuer and must not upload the packet.
- No service-account key, plaintext secret, secret version, Cloud SQL user,
  Cloud Run service/job, scheduler, public IAM, corpus, OCR, model or Chat
  activation is in scope.
- The operator principal is one exact private user or service account. Its
  TokenCreator grant has an absolute RFC3339 expiry no more than four hours
  after the packet issue time.
- Code/validate does not authorize apply. A saved create-only plan needs active
  cloud/state leases, independent correctness/risk review and named human
  Cloud Operator authorization.
- VFBIZ-0216 `--apply` remains blocked until its repeated-unknown Cloud SQL
  credential recovery protocol is independently accepted.

## Done when

- Terraform fails closed unless packet work ID, action, environment, project,
  region, instance, database, secret, bucket, authority digest, object name,
  generation, issue/expiry, claim/fencing token and both foundation plan
  digests are complete and mutually consistent.
- A dedicated service account has only Cloud SQL read/user-update/operation
  polling, exact administrator-secret read/list/add/access and evidence-bucket
  metadata/create/get permissions. It has no delete, list-objects, key, runtime
  secret, job or public authority.
- Impersonation is conditional on packet expiry and never granted when the lane
  is disabled or the principal is empty.
- Default plan remains no-change. Any enabled saved plan is create-only, has
  zero update/delete/replace/public IAM and creates no secret payload or
  workload.
- Focused permission tests, OpenTofu formatting/validation, governance and two
  independent review recommendations pass before any apply disposition.

## Checkpoint

- Coordination `coord-4e2c916d-8d44-424e-aa8b-989d5eb6e87e` records the
  Reliability Engineering recommendation to own only the `infra/gcp` writer
  lane while VFBIZ-0216 remains owned by AI Platform Foundation.
- VFBIZ-0216 commit `415316b` is dry-run-only. Its final correctness/risk cycle
  rejects credential mutation until immutable authority, least-privilege ADC,
  exclusive execution and recoverable repeated-ambiguity evidence exist.
- Commits `03d0135` and `8ec2c8e` add native authority tests and close the
  authority-prefix self-mint, project-wide Cloud SQL update and stale saved-plan
  expiry findings. The evidence writer is limited to the exact completion
  witness, Cloud SQL is bound to the exact development instance, and the gate
  revalidates time at both plan and apply.
- OpenTofu format/validation and four focused native tests pass. Saved default
  plan SHA-256
  `2f0ed17968ea98986facee785f5a7fa3aa1270738c190b67f52ea68cccd98336`
  contains exactly 53 no-ops and no create, update, delete or replace action. No
  cloud mutation was applied.
- Final correctness and risk reviews are recommendation-only. They retain P1
  claim-liveness/ADC binding and P2 operation-polling compatibility findings;
  VFBIZ-0216 repeated-unknown credential recovery is still unresolved.
- Coordination `coord-96397585-df19-49c3-9a8c-80ad56ba95e1` records the
  cross-owner evidence handoff. This checkpoint records code/test/review only;
  it grants no apply or release authority.
- Exact next action: define a new reviewed execution protocol that validates
  the active claim, current fencing token and exact ADC identity immediately
  before apply, and separates instance-scoped mutation from operation polling.
  Do not enable or apply this lane while either finding remains.

## Evidence

- [x] Cross-team coordination and read-only Reliability recommendation.
- [x] Default-off authority and identity IaC; default saved plan is no-change.
- [x] Focused permission and negative configuration tests.
- [ ] Enabled create-only saved plan; the default no-change plan is sealed.
- [x] Independent correctness and risk recommendations; both recommend hold.
- [ ] Named human apply disposition and post-apply no-change evidence.
