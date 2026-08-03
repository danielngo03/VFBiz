---
id: VFBIZ-0210
title: Reconcile GCP IaC and provision Vertex smoke identity
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
  - infra/gcp/main.tf
  - infra/gcp/vertex_smoke.tf
  - infra/gcp/outputs.tf
  - infra/gcp/README.md
  - docs/work/items/VFBIZ-0210.md
  - WORK.md
depends_on: []
controlled_signals:
  - iam
  - ai-provider
  - ai-budget-policy
exclusive_resources:
  - gcp-iam
  - gcp-terraform-state
required_checks:
  - npm run governance:check
  - tofu -chdir=infra/gcp validate
  - tofu -chdir=infra/gcp plan
revision: 4
review_date: "2026-08-31"
updated_at: "2026-07-31T02:45:38Z"
---

# Outcome

Reconcile the imported GCP development state to a no-destroy OpenTofu plan,
then provision one keyless `vfbiz-vertex-smoke` service account with only the
minimum online Vertex prediction permission needed by VFBIZ-0209.

## Constraints

- Project is exactly `vinfast-503003` (`81588547131`), region
  `asia-southeast1`, remote state bucket
  `vinfast-503003-vfbiz-tfstate-dev`, prefix `vfbiz-ai/development`.
- The user explicitly authorizes development IAM changes. No production scope,
  public IAM, service-account key, broad Owner/Editor role or workload
  activation is authorized.
- Preserve all imported buckets, topics, subscription, Document AI processor,
  budget and existing worker bindings. State moves/imports must reflect
  existing resources and may not recreate them.
- Stop before apply if plan includes any destroy/replacement, removes an
  existing permission, weakens public-access prevention, changes the 4,000,000
  VND project budget or enables Cloud Run.
- The smoke service account may receive only a custom role containing
  `aiplatform.endpoints.predict`; it receives no storage, Document AI, Pub/Sub,
  dataset, tuning, pipeline, model upload, endpoint create/deploy or batch
  authority.
- Use ADC and service-account impersonation; never create a JSON key or commit
  backend configuration, state, credentials, account secrets or provider
  output.

## Done when

- Configuration represents every currently imported resource without deletion
  or forced replacement.
- A saved plan has zero destroy/replacement and only the reviewed smoke service
  account, custom prediction role and exact binding as additions.
- `tofu validate` and the saved plan inspection pass before apply.
- Apply uses the saved plan, then a fresh plan returns no drift.
- IAM evidence proves the principal identity and exact effective permission
  relevant to online prediction; the evidence is hashed and contains no token.
- Independent risk review recommends or blocks the exact plan; agent review is
  recorded as recommendation, not human approval.

## Checkpoint

- The reviewed targeted plan
  `sha256:8e271b6e98cefdcea77400c8d0c2a889cd0832ac86607949f22fff65e465ce3b`
  applied exactly four creates and zero update/delete/replace. The dedicated
  identity, prediction-only custom role and two exact bindings now exist.
- Post-apply targeted plan is clean. Remote state remains on the original
  lineage at serial 19; the state snapshot digest is
  `sha256:fe6a80d43de700bb0f0644e9c8fb04fd8bde3167abf3247510bc3d99597a3bce`.
- A fresh un-targeted plan still contains seven VFBIZ-0199 additions and the
  existing subscription acknowledgement change from 60 to 300 seconds. It has
  zero destroy, but is outside this reviewed apply and prevents claiming full
  module no-drift.
- Exact next action: reconcile the seven additions and acknowledgement change
  under the owning VFBIZ-0199 scope. Never reuse either saved plan.

## Evidence

- [ ] `npm run governance:check` — pending after final checkpoint
- [x] `tofu -chdir=infra/gcp validate` — observed green before apply
- [x] reviewed targeted apply — 4 added, 0 changed, 0 destroyed
- [x] post-apply targeted plan — no changes
- [ ] full `tofu -chdir=infra/gcp plan` — 7 add, 1 change, 0 destroy;
  remaining VFBIZ-0199 reconciliation is explicitly not accepted

### ready — 2026-07-31T02:31:54.478Z

Existing GCP resources and remote state are known; development IAM authorization is explicit and all destructive plan actions are stop conditions.

### active — 2026-07-31T02:31:54.621Z

Begin state/config reconciliation; do not apply until a no-destroy saved plan is reviewed.

### post-apply checkpoint — 2026-07-31T02:45:38Z

Reviewer-verifier and risk-reviewer independently accepted only the targeted
plan by the same digest. The plan artifact permission finding was resolved from
`0644` to `0600` before apply. Cloud evidence proves one dedicated service
account, one custom role containing only `aiplatform.endpoints.predict`, one
project binding, one explicit operator TokenCreator binding represented by
principal digest
`sha256:8d2193a73a8bbd30c6ae9e28dbad1678334596d90504a37eb3763e1a322d7958`,
zero public member and zero user-managed service-account keys. These are
technical recommendations and observed evidence, not release approval.
