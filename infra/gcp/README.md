# VFBiz GCP development foundation

This directory is the infrastructure boundary for the VinFast AI development
project. It imports the already-created development resources; it does not
upload corpus data, enable public access, or submit model jobs.

The first apply is an import/reconciliation operation. Bootstrap one dedicated,
private, versioned GCS state bucket, then initialize the partial `gcs` backend
with operator-supplied `bucket` and `prefix` values. Do not reuse intake,
derived or evidence buckets for state because workload identities can access
those data planes. Run `tofu plan` and confirm that no bucket, topic,
subscription, service account or processor will be replaced before any apply.
Never commit backend configuration, state, credentials or provider output.

The intake, derived-staging, dedicated OCR-output and evidence buckets are
not the complete production trust-zone set. The worker writes only to the
derived-staging bucket, while Document AI output and reconciler list access
are isolated in the dedicated OCR-output bucket. This bucket boundary is
intentional: GCS object-list permissions cannot be safely narrowed to an
object prefix with the current IAM condition, so the reconciler must never
share a bucket with worker staging objects.
Before a Dataset Release, add distinct buckets or an approved equivalent for
each trust zone and update the AI registry mapping.

```sh
cp terraform.tfvars.example terraform.tfvars
# Fill values from the private operator packet.
tofu init \
  -backend-config="bucket=REPLACE_WITH_PRIVATE_STATE_BUCKET" \
  -backend-config="prefix=vfbiz-ai/development"
tofu validate
tofu plan
```

The Cloud Run worker remains disabled until an immutable `worker_image`, an
existing Secret Manager ID, its exact numeric version and a reviewed synthetic
manifest are supplied by a deployment packet. The packet must also pin its
content-free GCS generation/digest, the reviewed saved-plan digest, rollback
image digest and named Document AI risk-disposition evidence. Terraform keeps
both workloads disabled until every one of those packet fields is present and
well-formed. Pub/Sub dispatch is a separate
`worker_dispatch_enabled` switch, so an operator can stop delivery without
destroying the service or its evidence. Terraform derives the exact private
endpoint and OIDC audience from Cloud Run and uses a dedicated push-only
service account. The worker uses a durable submission reservation so an
ambiguous provider call is reviewed or dead-lettered instead of being silently
submitted twice. The subscription still has bounded retry and a dedicated
dead-letter topic while dispatch is disabled. No real VinFast content belongs
in this development foundation before the source and purpose gates pass.

Before filling `terraform.tfvars`, validate the content-free packet itself:

```sh
cd backend/ai
uv run python scripts/validate_gcp_activation_packet.py \
  --packet /private/operator/path/vfbiz-0199-activation.json
```

The command emits only packet and evidence digests. It rejects unknown fields,
secret values, raw content, self-resigned digests, plan destruction or
replacement, duplicate runtime secrets, enabled switches and invalid GCS
generation/URI values. Its output is an input to the reviewed Terraform plan,
not an approval or an automatic apply.

Document AI reconciliation is not exposed as another HTTP route on the Pub/Sub
worker. A separate Cloud Run Job runs one bounded batch with its own service
account and restricted PostgreSQL secret. Cloud Scheduler is independently
disabled by default; enabling it cannot implicitly enable the job or worker
dispatch.

The worker and reconciler must reference different Secret Manager IDs backed
by different PostgreSQL login roles. Both secret references pin a positive
numeric version. Terraform rejects a deployment packet that reuses one secret
for both workloads. Document AI permissions are also split: the worker can
submit batches while the reconciler can only read operation state. The
application request pins one exact processor version, but these custom IAM
permissions remain project-scoped because Document AI resource attributes are
not supported by IAM Conditions. Neither identity receives the broader
predefined Document AI API user role. A named development risk disposition is
therefore still required before deployment. Artifact Registry cleanup policies
remain dry-run until rollback digests and retention are independently reviewed.

The private development database foundation is a separate, default-off lane.
Setting `database_foundation_enabled=true` plans one PostgreSQL 17 shared-core
Zonal instance with a fixed 20 GiB disk, seven retained backups, no public IPv4,
encrypted connections, deletion protection, a dedicated VPC/subnet and Private
Services Access. Cloud Run uses Direct VPC egress to that subnet; no VPC
connector is created. The foundation creates three empty, deletion-protected
Secret Manager containers for bootstrap, submitter and reconciler URLs. Each
container has one user-managed replica in `asia-southeast1`; automatic
multi-region replication is not allowed. The foundation does not create SQL
users, passwords or secret versions. A later private
bootstrap job must run the reviewed migrations and role provisioner before it
may publish exact numeric versions. That manual-only job uses a separate
digest-pinned image and service account, reads only the exact administrator
secret version and may add/disable versions only on the two runtime secret
containers. It has no scheduler or invoker binding here. Migration
`20260802_0025` reserves one immutable database epoch before any external secret
write, so concurrent or repeated execution is rejected; credential rotation is
a separate future workflow. Consequently, enabling only the foundation still
cannot create the bootstrap job, worker service, reconciler job, push dispatch
or schedule.

The administrator credential operator is a third, separately default-off lane.
It never creates the authority packet: a named Cloud Operator must publish one
canonical, content-free JSON object with a create-only generation precondition.
IaC reads that exact object, recomputes its SHA-256 and binds its GCS generation,
work item, one action, Singapore resources, reviewed foundation plans, active
claim/fencing token, operator principal and maximum four-hour expiry before it
can create a dedicated keyless identity. That identity receives only Cloud SQL
database/instance inspection, SQL-user credential update and operation polling;
exact administrator-secret get/list/add/access; and evidence-bucket
metadata/create/get. It has no object list/delete/update, runtime-secret, Cloud
Run, scheduler, public IAM or service-account key authority. Its conditional
impersonation grant expires with the packet. Enabling this identity does not
authorize running the credential operator; the lane remains blocked until a
reviewed create-only saved plan and the separate repeated-ambiguity recovery
gate are both accepted.

Always review two plans for this lane: the normal/default-off plan must report
`No changes`, while the explicit enabled plan must be create-only and contain
no workload, public IAM, SQL user, secret payload, update, replacement or
deletion. Applying the enabled plan starts a billable Cloud SQL instance and is
therefore an operator decision after independent plan and cost review; it is
not implied by validating this configuration.

The reconciled worker identity is intentionally narrow: it can get an exact
intake object, create/get a derived object and publish a structured DLQ record.
It has no evidence-bucket access, subscription pull role or TokenCreator
binding. Pub/Sub can mint OIDC only for the dedicated push identity. Legacy
bucket and worker-impersonation bindings were imported into state before their
reviewed removal; the post-transition refresh-only and normal plans are clean.
