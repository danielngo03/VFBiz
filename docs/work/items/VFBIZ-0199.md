---
id: VFBIZ-0199
title: Codify GCP knowledge ingestion development foundation
status: active
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - infra
  - root
allowed_paths:
  - backend/ai/app/modules/datasets
  - backend/ai/app/modules/knowledge
  - backend/ai/ops/gcp-intake-worker
  - backend/ai/app/infrastructure
  - backend/ai/app/platform
  - backend/ai/migrations/versions/20260730_0021_document_ai_submission_ledger.py
  - backend/ai/migrations/versions/20260801_0023_document_ai_reconciliation_evidence.py
  - backend/ai/migrations/versions/20260802_0024_document_ai_runtime_roles.py
  - backend/ai/migrations/versions/20260802_0025_document_ai_database_bootstrap_epoch.py
  - backend/ai/scripts
  - backend/ai/tests
  - backend/ai/docs/knowledge-ingestion.md
  - local-data/ai-datasets/candidate/knowledge
  - local-data/ai-datasets/quarantine/synthetic/document-ai-pilot-v1
  - local-data/ai-datasets/archive/rejected/knowledge
  - local-data/ai-datasets/tombstones/candidate-knowledge
  - contracts/ai/datasets/sources
  - contracts/ai/index.json
  - contracts/ai/test-vectors/dataset-contracts.json
  - infra/gcp
  - .agents/skills/operate-gcp-ai
  - docs/INDEX.json
  - docs/INDEX.md
  - docs/work/plans/vivi-gcp-ai-platform.md
  - docs/work/items/VFBIZ-0199.md
  - WORK.md
depends_on:
  - VFBIZ-0198
controlled_signals:
  - ai-dataset
  - dataset-source
  - knowledge-ingestion
  - cloud-infrastructure
  - public-contract
exclusive_resources:
  - ai-source-intake-contract
  - ai-dataset-registry
  - gcp-vinfast-development
  - terraform-state
required_checks:
  - npm run contracts:lint
  - npm run verify:ai
  - npm run verify:ai:integration
  - npm run governance:check
revision: 59
review_date: "2026-08-30"
updated_at: "2026-08-03T01:30:00+07:00"
---

# Outcome

Provide a fail-closed, idempotent GCS/Pub/Sub/Document AI development pipeline
with immutable receipts, bounded cost and infrastructure drift evidence.

## Constraints

- No real VinFast content is uploaded until the source gate resolves exact
  Content/Legal/Data authority.
- Existing cloud resources are imported into IaC and never silently replaced.
- The worker uses workload identity; service-account keys and secrets never
  enter Git.
- Development processing cannot create a Dataset or Knowledge Release.

## Done when

- Managed upload, local bootstrap and external HTTPS have distinct provenance
  and release policies.
- GCS create and replay paths verify generation, SHA-256, size and CRC32C.
- GCS reader, Pub/Sub envelope, Document AI submit/reconcile and DLQ ports have
  deterministic fake tests and one synthetic live smoke packet.
- Local/development candidates cannot materialize into the active retriever.
- Terraform represents buckets, IAM, Pub/Sub, OCR processor, budget and bounded
  Cloud Run workers without replacement drift.
- Required checks and independent correctness/risk reviews pass.

## Checkpoint

- Current checkpoint (2026-08-03, Revision 59): the worker staging boundary is
  `vinfast-503003-derived-dev`; Document AI raw output/reconciler list boundary
  is the separate `vinfast-503003-ocr-output-dev`. Runtime settings and the
  composition test enforce the split. IaC keeps the output bucket default-off
  behind `ocr_output_bucket_enabled`, with workload lifecycle guards and no
  public or provider activation.
- Revision-50 adds an IaC activation-packet gate. Worker and reconciler
  lifecycle readiness now requires a content-free authority packet digest and
  exact GCS generation, reviewed saved-plan digest, rollback image digest and
  named Document AI risk-disposition digest/reference. All values default to
  empty, so the current development foundation remains disabled; a partial or
  guessed packet cannot create a workload.
- Revision-51 adds `scripts/validate_gcp_activation_packet.py`, an independent
  canonical validator for the content-free operator packet. It emits only
  packet/evidence identities and rejects self-resigned digests, unknown/raw
  fields, secret values, duplicate runtime secrets, plan destruction or
  replacement and enabled switches. It performs no cloud mutation.
- Revision-52 adds the provider-neutral downstream Document AI materialization
  boundary. It routes provider-review or scan-rejected pages to review, runs
  chunking and embedding only for passed pages, verifies embedding lineage
  before one atomic candidate sink call, and never activates a retriever or
  public Chat. Focused and full AI checks are green; no cloud call or real
  corpus was used.
- Revision-53 closes a partial-document readiness gap: any page requiring
  review now keeps the whole extraction `review-required`, so a mixed or
  incomplete document cannot be treated as candidate-ready. The materializer
  also pins scanner/policy/chunker/embedding revisions and rejects scan
  evidence from a different authority before chunking.
- Revision-54 aligns `backend/ai/docs/knowledge-ingestion.md` with the new
  materialization boundary: page lineage is complete before downstream work,
  and no partial document can be promoted as `candidate-ready`.
- Revision-55 completes the cross-workspace verification pass after the
  materialization boundary: `verify:api` passes lint, typecheck, 73 unit suites
  (478 tests), 11 E2E suites (76 tests), Prisma validation and build; both
  customer and workforce portals pass lint, typecheck, unit/integration tests
  and production builds. `contracts:lint`, `governance:check` and
  `git diff --check` remain green. These are local deterministic checks only;
  they do not constitute GCP deployment, source approval or release authority.
- Revision-56 aligns all Document AI unit/reconciliation/worker fixtures with
  the dedicated `vinfast-503003-ocr-output-dev` boundary; `derived-dev` remains
  reserved for staged input. The focused GCP submit/output/reconciliation
  suite passes 39 tests, with no cloud request or resource mutation. This
  closes the test-boundary drift noted by independent ingestion review; it
  does not satisfy the operator activation gate.
- Revision-57 closes the remaining output-boundary drift in materialization and
  PostgreSQL submission-ledger fixtures: OCR output prefixes/forged output URIs
  now use `vinfast-503003-ocr-output-dev`, while staged input fixtures remain in
  `derived-dev`. The expanded focused suite passes 46 tests with 8 expected
  database-configuration skips. Independent risk review confirms no cloud/IAM
  mutation and retains the pre-existing stale IAM/Document AI permission gate.
- Revision-58 records independent correctness and risk review: a global scan
  found no remaining P0–P2 fixture-boundary drift; all Document AI output
  prefixes/URIs use `ocr-output-dev`, while `derived-dev` is limited to staging,
  negative-boundary or settings-rejection fixtures. The direct focused command
  passed 46 tests with 8 expected PostgreSQL-configuration skips; independent
  broader reviewer scopes also passed (49 and 65 tests respectively) with no
  cloud mutation. Existing stale IAM and project-scoped Document AI permission
  remain activation gates.
- Revision-59 strengthens the candidate materialization receipt: the sink and
  summary now persist source generation/metageneration, Document AI processor,
  scanner, policy, chunker and embedding revisions. The materializer still
  writes only after complete page/scan/chunk/embedding checks; focused lineage
  tests pass and no runtime/cloud behavior changed.
- Changed paths in this continuation: `infra/gcp/main.tf`, `outputs.tf`,
  `variables.tf`, `terraform.tfvars.example`, `README.md`, AI GCP settings and
  runtime composition, GCP IAM/settings tests, the provider-neutral
  `cloud_materialization` application boundary and its focused tests,
  ingestion documentation and this work item. No raw PDF/OCR/chunk/vector file
  changed.
- Observed checks: `verify:ai` is green with 982 passed, 112 conditional skips
  and one known Starlette/httpx warning; focused IAM/ingestion/object-store
  suite is 42 passed and the direct dedicated output-boundary suite is 46
  passed with 8 expected DB skips; independent reviewer scopes passed without
  new findings;
  `verify:api` and `verify:apps` are green;
  `contracts:lint`, `governance:check`, `docs:check`, `tofu fmt -check
  -recursive`, `tofu validate` and `git diff --check` pass.
  A lock-protected read-only OpenTofu plan acquired/released the remote lock
  normally and is recorded below; no apply occurred.
- Exact next action: a named Cloud/IaC operator must review the default-off
  plan's two stale disabled-worker IAM removals and any explicit
  `ocr_output_bucket_enabled=true` plan. Before activation, reconcile the
  legacy project-scoped Document AI grant, runtime SQL identities/secret
  versions, image provenance/scanning, hard cost stop and Data Owner retention
  decision. Do not upload real corpus, enable OCR/worker dispatch or activate
  public Chat from this checkpoint.
- Additional read-only evidence (Revision 48): a refresh-free simulation with
  `ocr_output_bucket_enabled=true` plans exactly one OCR-output bucket create,
  one role-description update and the two stale disabled-worker IAM removals;
  no Cloud Run service, Pub/Sub push, scheduler or database secret is enabled.
  Plan artifact: `/tmp/vfbiz-0199-r47-output-bucket.tfplan` (SHA-256
  `a3f6b183ea8e830ccaa05a358b159f0533d79d5c4b9ead54ed737cff8b7940b0`). This
  simulation was not applied and is not activation approval.

- Revision-49 regression evidence: the retrieval bake-off authority now binds
  ordered held-out cases to one source-release digest, index-generation
  digest, evaluator revision and canonical suite digest. No cloud plan was
  applied and no corpus or provider request was issued.

- Revision 23 records the project owner's explicit development Cloud Operator
  authorization within the existing 4,000,000 VND monthly guardrail. This
  authority covers the exact private foundation plan only; it does not grant a
  Data/Privacy source decision, secret payload, workload activation, OCR,
  tuning, Dataset Release or public Chat authority.
- Saved OpenTofu plan R23 SHA-256
  `9bb0f86fe93f1882ea0a875b31df3295a06d166af1eaf735495ca528d0bfe04f`
  contained exactly 13 creates and 40 no-ops with zero update, delete,
  replacement, public IAM, Cloud Run/Scheduler/Pub/Sub workload, SQL user or
  Secret Manager version. Independent risk evidence fingerprint
  `1282f60804938c52a16434c8dc8a84a67c5c6a0373234d81d01fad3b10f877c5`
  returned `APPLY-EXACT` with no new P0/P1/P2.
- The exact saved plan applied successfully: 13 added, zero changed and zero
  destroyed. It created a private Singapore VPC/subnet/Private Service Access,
  three required APIs, one PostgreSQL 17 `db-f1-micro` Zonal instance with a
  fixed 20 GiB disk, seven retained backups, deletion protection, no public
  IPv4 and `ENCRYPTED_ONLY`, one empty `vfbiz_ai` database and three empty
  deletion-protected Secret Manager containers with single-region
  `asia-southeast1` replication.
- Private operator values now persist `database_foundation_enabled=true` so a
  default plan cannot propose destroying the enabled foundation. The ignored
  values file contains no newly added credential or secret payload.
- Post-apply plan SHA-256
  `878381f284660f5f4558db53b9baca5ae65dcd5346b1198eee11431fd2b2bb4b`
  reports `No changes`. Live SQL state is `RUNNABLE` at private address
  `10.89.0.3`; all three secret containers have zero versions; Cloud Run has
  zero services/jobs; worker subscription `pushConfig` remains empty and both
  worker dispatch and reconciliation schedule remain disabled.
- Official current Singapore list pricing estimates the always-on shared-core
  instance plus 20 GiB SSD and up to 20 GiB used backup at about USD 21.5 per
  month before network. The existing billing budget remains exactly 4,000,000
  VND with alerts at 50/75/90/100 percent. This is development capacity without
  an SLA or production recovery claim.
- The next activation step is intentionally not an ad-hoc password command.
  It requires a reviewed, content-free administrator credential bootstrap that
  sets the Cloud SQL administrator credential and writes only numeric Secret
  Manager version evidence without exposing a database URL in shell arguments,
  logs, Git or `.env`. Only then may the digest-pinned one-shot migration and
  restricted-identity Cloud Run Job be planned. Worker, OCR and corpus dispatch
  remain disabled.


- GCP project `vinfast-503003` and bootstrap resources exist in
  `asia-southeast1`; no real VinFast corpus object has been uploaded.
- Source intake now separates `external-https`, `managed-upload` and
  `local-bootstrap`; managed uploads are quarantine-only and not developer-only
  local bootstrap receipts.
- GCS object I/O now verifies create success, replay, generation, SHA-256, size
  and CRC32C; Pub/Sub, DLQ and Document AI job receipts are pointer-only.
- Development knowledge releases now reject unapproved local/managed source
  candidates before materialization.
- OpenTofu `1.12.5` is installed locally. The `infra/gcp` partial GCS backend
  is initialized against the private state bucket
  `gs://vinfast-503003-vfbiz-tfstate-dev` with prefix `vfbiz-ai/development`.
- Existing buckets, worker service account, intake topic/subscription, OCR
  processor and development budget are imported into remote state. IAM API was
  enabled for `vinfast-503003` because provider refresh required it.
- Reconciliation apply completed with 8 adds, 6 in-place changes and 0
  destroys. Added/updated resources were DLQ topic, bounded Pub/Sub retry and
  dead-letter policy, least-privilege worker bucket access, Pub/Sub service
  agent permissions, administrative labels and OCR processor abandon-on-delete
  state.
- Post-apply OpenTofu plan reports `No changes`; subscription
  `vinfast-document-worker-dev` points to DLQ
  `projects/vinfast-503003/topics/vinfast-document-intake-dlq-dev` with
  `maxDeliveryAttempts=5`, minimum retry backoff `10s` and maximum `600s`.
- Independent infrastructure review found the worker had no Document AI
  permission for OCR smoke. Added `roles/documentai.apiUser` to
  `vfbiz-ai-dev-worker@vinfast-503003.iam.gserviceaccount.com`, recovered the
  interrupted OpenTofu state write by pushing `errored.tfstate`, removed the
  local recovery state file and confirmed a post-recovery `No changes` plan.
- `npm run contracts:lint`, `npm run governance:check`,
  `npm run verify:ai` and `npm run verify:ai:integration` all passed after
  regenerating `docs/INDEX.{md,json}` from the current 79 documents.
- `npm run verify:api` now passes lint, typecheck, 387 unit tests, 67 E2E tests,
  Prisma validation and build. This verifies the private integration boundary;
  the public Chat API remains disabled.
- Synthetic live smoke uploaded only a repository fixture to the intake bucket,
  verified metadata, then removed the object; no OCR worker message was
  published because Cloud Run is not deployed.
- Independent risk review confirmed real corpus upload, Dataset Release, Golden
  binding, factual staging, supply-chain and public activation remain
  human-blocked. Automation may continue only for immutable worker image,
  authenticated Pub/Sub push, synthetic Pub/Sub/Document AI smoke and
  deterministic checks.
- A separate Cloud Run intake application now accepts only bounded pointer
  envelopes, revalidates exact content-addressed GCS generation/SHA-256/size/
  CRC32C/PDF metadata, submits pinned Document AI batches and sanitizes its
  acknowledgement. It is not mounted into the private AI application.
- Migration `20260730_0021` adds a durable submission reservation. Ambiguous
  provider outcomes become `DOCUMENT_AI_SUBMISSION_INDETERMINATE` and cannot be
  resubmitted automatically after a worker restart.
- Migration `20260730_0021` also rejects UPDATE mutations, DELETE and TRUNCATE.
  Daily OCR accounting uses an immutable application-authority `budget_date`,
  so an advisory-lock wait across UTC midnight cannot omit reserved pages.
- Cloud object identity now pins both generation and metageneration. A GCP
  worker cannot start without a reviewed synthetic manifest mapping an exact
  PDF SHA-256 to its independently observed page count; arbitrary Pub/Sub or
  mutable object metadata therefore cannot authorize OCR or reduce its charge.
- Pub/Sub acknowledgement and Cloud Run request deadlines are both 300 seconds;
  bounded generation-pinned rewrite calls fit inside that envelope.
- GCS runtime rights are custom create/get-only roles. Revision 11 also removes
  the broad predefined Document AI API user role: the worker custom role has
  only `documentai.processorVersions.processBatch`, while the reconciler custom
  role has only `documentai.operations.getLegacy`. Both bindings exist only
  when their corresponding workload prerequisites are complete.
- Independent correctness review confirmed the action-level separation but
  retained `VFBIZ-0199-R11-DOCUMENTAI-RESOURCE-SCOPE-001` as a deployment P1:
  Document AI is not listed among IAM Conditions resource-attribute services,
  so both custom permissions remain project-scoped. The application pins the
  exact processor/version endpoint, but that is not an IAM boundary. Deployment
  remains blocked on a named development risk disposition and post-apply proof
  that the live broad `roles/documentai.apiUser` binding was removed.
- Terraform now keeps both Cloud Run and push delivery disabled unless an
  immutable image digest, reviewed endpoint and existing PostgreSQL Secret
  Manager ID are all supplied. The database secret grant is created only with
  the worker.
- The initial local Linux/amd64 worker image was built from digest-pinned Python
  and uv bases. Its superseded local image ID was
  `sha256:73e5ae0bc04394ca976d7357bd4a01c3f431f94de1ec6bc7d815e042dbebc60a`;
  health passed as non-root UID/GID `65532`, and the image contains neither
  `local-data` nor tests. This local ID is not an Artifact Registry release
  digest and has not been deployed.
- The second and final independent review cycle found no P0. Its DB destruction,
  midnight accounting, mutable metadata, self-asserted page authority, broad
  GCS rights and deadline findings are corrected. Activation evidence and the
  project-scoped Document AI role remain explicit controlled gates.
- A fresh IAM audit found legacy worker access outside the intended push
  boundary: Pub/Sub could mint tokens as the OCR worker, and broad
  `objectViewer`/`objectUser` bindings remained on intake, derived and evidence
  buckets. The two unmanaged bindings were imported into remote state before
  removal; no out-of-band IAM deletion was used.
- Risk review rejected the first reconciliation plan and approved only saved
  plan R13 (`b6939c771bc0f72943325d13a2461803766cd0311c2ee50f9f9d8da5f81314fe`).
  Its exact apply completed with 7 creates, one in-place subscription update,
  7 intentional legacy-IAM deletes and zero replacements.
- Live verification now shows worker access limited to intake `objects.get`,
  derived `objects.create/get` and DLQ publish; it has no evidence-bucket
  access, subscription pull role or TokenCreator binding. Pub/Sub can mint OIDC
  only for the dedicated push identity. Push remains disabled and no Cloud Run,
  corpus, endpoint, dataset or tuning resource was created.
- Refresh-only state reconciliation changed no remote resource. Both the final
  refresh-only plan and normal plan report `No changes`.
- Local PDF processing no longer has a Tesseract implementation, container or
  test surface. Local bootstrap is intake/quarantine-only and records
  `awaiting-gcp-document-ai`; it cannot create parsed pages or candidate chunks.
- Release-ineligible local knowledge retirement now requires an exact manifest,
  `active_retriever_visible=false`, symlink-free inventory and an atomic move to
  a recoverable trash destination. A minimal content-addressed tombstone records
  the manifest/tree digest, file/byte/chunk counts and actor reference without
  deleting source quarantine objects or intake receipts.
- Candidate batch `vinfast-customer-docs-20260730` was atomically retired to
  macOS Trash with recovery token
  `VFBiz-candidate-knowledge-0d73815c8a7dbe4d`: 10,884 files, 31,330,952 bytes
  and 10,805 chunks. Candidate knowledge now contains zero files while the 79
  content-addressed quarantine PDFs remain intact.
- The existing local intake was re-imported idempotently after retirement. Its
  v2 processing handoff now records exactly 79 documents as
  `awaiting-gcp-document-ai`, zero locally processed documents and zero local
  candidate outputs.
- A bounded Document AI output reader is now runtime-composed separately from
  submit/reconcile. It lists only the receipt output prefix, revalidates exact
  GCS generation/metageneration/size/CRC32C, recomputes CRC32C and SHA-256 while
  downloading, parses official `Document` JSON shards and proves exact 1-based
  page completeness. Low-confidence or short-text pages become
  `review-required`; the reader does not chunk/embed or claim perfect OCR.
- The Document AI request now uses a bounded field mask for document text,
  page number/layout/token confidence, shard information and provider error;
  image payloads and unrelated enrichment are not requested.
- Revision 24 closes review finding `GCS-SHA-UNBOUND-001` in the pre-submit
  source verifier: it now streams the exact generation with `alt=media`,
  recomputes SHA-256 over the bytes under a bounded source-size limit, and
  rejects `GCS_OBJECT_CONTENT_MISMATCH` before any OCR provider call. A
  regression test proves forged custom `sha256` metadata cannot authorize
  different bytes. Focused ingestion, worker, reconciler and IAM architecture
  tests pass (41 tests).
- The same integrity boundary now applies to the shared `GcsTrustZoneObjectStore`:
  create-success and 412 replay paths stream the generation-pinned payload and
  verify SHA-256, size and CRC32C before returning a `StoredObject`; GCS
  objects persist generation/metageneration and replay without a generation is
  rejected. Regression coverage includes forged replay bytes.
- Independent review still retains activation blockers: project-scoped legacy
  `roles/documentai.apiUser`, broad bucket-level object permissions, missing
  source-rights/ACL approval joins for real corpus, and retention/cost
  enforcement decisions. These are not silently waived.
- Post-fix reviewer verdict closes `GCS-SHA-UNBOUND-001` and
  `GCS-GENERATION-PERSIST-002` for the reviewed paths: source verification and
  shared-object replay now re-hash generation-pinned bytes, persist generation
  and metageneration when observed, and enforce generation/metageneration
  preconditions on media reads. No new P1 was found in this delta. Provider
  responses that omit metageneration remain a minor compatibility P2 and are
  not treated as a reason to activate the worker.
- The ignored local `derived-quarantine` tree still contains 3,800 legacy
  Tesseract-derived page artifacts. They are not consumed by the current
  Document AI-only runtime and are outside the active candidate tree; a
  separate inventory/tombstone decision is required before claiming the local
  workspace contains no raw OCR artifacts.
- Revision 25 adds GCS IAM Conditions to the worker/reconciler bucket bindings:
  intake reads are limited to `objects/sha256/`, worker staging is limited to
  `objects/document-ai-input/`, and reconciliation is limited to
  `objects/document-ai/jobs/`. The latter prefix was checked against the
  runtime output builder after an independent review caught an initial
  `objects/jobs/` mismatch; the corrected configuration passes `tofu validate`
  and the focused IAM/ingestion/object-store suite (39 tests). No plan/apply or
  cloud IAM mutation was performed.
- Independent risk recheck passes the corrected prefixes and confirms the
  runtime/output-reader alignment. The live project still requires a reviewed
  no-destroy plan/apply plus post-apply IAM condition and synthetic list/read
  verification; existing broad bindings are not claimed removed until that
  evidence exists.
- A read-only OpenTofu plan against the live imported state now shows only two
  IAM-member replacements (worker intake and worker derived writer) required
  to attach the new Conditions; no workload, bucket, database, secret,
  processor or public-IAM change is planned. Because Terraform models a
  condition change as destroy/create of the IAM membership, this plan is not
  applied automatically and requires the named Cloud Operator's reviewed
  no-data-loss packet plus post-apply synthetic list/read proof.
- The default-off plan was tightened further: worker intake/derived bucket
  bindings now have `count = local.worker_service_enabled ? 1 : 0`, so a
  disabled worker receives no bucket access at all. The current read-only plan
  consequently proposes exactly two IAM-member destroys and zero creates,
  updates or replacements; the conditional bindings will be created only in a
  later explicitly enabled worker plan. This is staged code/IaC evidence, not
  an applied access change.
- Revision 28 makes provider `metageneration` mandatory in the shared GCS
  metadata verifier and always sends `ifMetagenerationMatch` on media reads.
  Local/in-memory `StoredObject` values may still omit cloud generations, but
  every GCS-created object carries both values. Object-store, Document AI and
  IAM architecture checks remain green.
- Migration `20260801_0023` now stores append-only Document AI operation
  observations and content-free extraction evidence. PostgreSQL recomputes the
  canonical SHA-256, binds every observation to its immutable submission,
  requires a succeeded terminal observation before extraction evidence, proves
  exact page completeness and rejects UPDATE, DELETE and TRUNCATE.
- A bounded reconciliation endpoint processes at most five pending jobs per
  invocation (one by default). It persists the provider observation before
  reading output, so a restart after provider success resumes from the exact
  terminal receipt without resubmission or duplicate OCR. A succeeded job stays
  pending until its extraction evidence is durably recorded.
- Extraction evidence stores only page text hashes, UTF-8 byte counts,
  confidence, review disposition and exact GCS output lineage. Raw OCR text is
  never persisted in the reconciliation ledger or returned by the operator
  endpoint. Both application and PostgreSQL require every output object/page to
  remain under the exact immutable submission output prefix.
- Canonical extraction confidence is stored as integer `confidence_micros`, so
  Python and PostgreSQL cannot disagree on scientific-notation JSON floats.
  Database triggers require exact top-level/page/output key sets and reject
  missing optional keys, extra raw-text/provider payloads and self-digested
  foreign-prefix evidence.
- PostgreSQL now claims each reconciliation job with an owner token, 300-second
  lease and monotonically increasing fencing token. Claim acquisition is
  transaction-serialized; restart waits for lease expiry, and concurrent
  reconcilers cannot consume multiple retries for one outage.
- Reconciliation failures are append-only evidence. Permanent failures are
  quarantined immediately; transient failures use 30/60-second backoff and the
  third attempt quarantines. Per-item batch isolation prevents one poison output
  from starving later jobs.
- OCR page validation now rejects over-sized text with a content-free typed
  error, translates provider HTTP outages to transient codes and enforces
  bounded output object/count/aggregate-text limits sized for the 1 GiB worker.
- Every successful provider HTTP response crosses one bounded JSON-object
  decoder. Malformed JSON becomes a content-free typed failure without the raw
  response or parser exception being attached to operator evidence.
- Output reconciliation has a 180-second global read deadline inside the
  300-second claim/Cloud Run envelope and accepts at most 20 output objects per
  invocation. Each provider timeout is capped by the remaining monotonic
  budget, and checks after JSON decode, page normalization, sorting and final
  evidence construction prevent tail work from returning success after the
  deadline. The 20-object ceiling is an application invariant, not a
  deployment-only default. Deadline exhaustion is retryable evidence rather
  than an unbounded sequence of provider calls.
- Every evidence write carries the exact owner and monotonically increasing
  fencing token acquired with the job. A reclaimed job rejects stale writers;
  the original owner may still persist typed deadline evidence after its lease
  expires only while no newer owner/fence has claimed the job. Migration
  downgrade refuses active unreleased claims as well as immutable evidence.
- IaC now stages a development derived-bucket lifecycle (live objects 7 days,
  noncurrent versions 1 day, soft-delete disabled). This is validated but not
  applied until a saved no-destroy plan is reviewed; production retention still
  requires a Data Owner decision.
- Final independent risk review closed both provider-decode and claim/deadline
  findings with no new P0/P1. Independent correctness review then reproduced a
  tail-deadline overrun and configurable object-cap gap; both were fixed and
  regression-tested. Its second and final pass reports no remaining findings
  in this reconciliation delta. These are technical recommendations only and
  do not approve IAM, real-corpus processing or release.
- A date-sensitive PostgreSQL integration fixture now uses the live UTC clock
  only when issuing a lease. The former fixed 31 July timestamp expired on 1
  August and correctly tripped the DB lease trigger; no trigger was weakened.
- Revision 29 repository gates are green after the generation/metageneration
  hardening: `verify:ai` reports 947 passed, 112 conditional skips and the
  existing Starlette/httpx compatibility warning; `contracts:lint`,
  `governance:check`, documentation checks, OpenTofu validation and
  `git diff --check` also pass. No cloud apply, upload, OCR dispatch, secret
  version or worker enablement occurred.
- Revision 30 re-ran the imported-state GCP preflight read-only. OpenTofu
  refresh-only observed provider-computed metadata drift but performed no
  remote action; the normal plan is `0 to add, 0 to change, 2 to destroy`,
  limited to the disabled worker's two bucket IAM members moved behind the
  conditional count. No workload, public IAM, processor, database or secret
  mutation is proposed, and the plan was not applied.
- Revision 31 focused integrity/IAM regression suite passes 39 tests covering
  generation-pinned object reads, SHA-256/CRC32C/metageneration checks,
  forged-source metadata, Document AI output lineage and IAM prefix
  conditions. This is local technical evidence only; live IAM remains
  unchanged pending the reviewed no-data-loss operator decision.
- Revision 32 read-only GCP IAM inspection confirms the remaining live drift:
  the disabled worker service account still has unconditioned custom reader
  access on `vinfast-503003-intake-dev` and custom writer access on
  `vinfast-503003-derived-dev`; it has no binding on the evidence bucket. The
  project-level `roles/documentai.apiUser` binding also remains. The saved
  normal plan's two destroys target the first two stale bucket bindings; no
  deletion was issued. Worker/push/OCR remain disabled until a named operator
  reviews the exact plan and post-change synthetic deny/list/read evidence.
- Revision 33 adds a read-only, content-free inventory for the ignored legacy
  derived tree. It records 78 source/pipeline trees, 3,800 page artifacts,
  7,273,813 bytes and 1,754 Tesseract-derived pages under inventory digest
  `2fbd60bc027d099e612f3971210fc5629ef3a4fac011f344ba0cdf68270c512a`. The
  report is stored with `0700/0600` permissions and contains no OCR text;
  `delete_performed=false`. No artifact was deleted or made retriever-visible;
  a separate reviewed tombstone/trash operation remains the next action.
- Revision 34 full AI gate passes 950 tests, 112 conditional skips and one
  existing Starlette/httpx deprecation warning; Ruff, Pyright and Alembic
  offline replay through migration `20260802_0025` are green. The new
  inventory command is included in this gate; no cloud provider call or local
  artifact deletion occurred.
- Revision 35 ran the complete PostgreSQL integration profile against a fresh
  disposable `pgvector/pg17` container. Alembic upgraded `0001` through
  `20260802_0025` and all 234 integration/evidence tests passed; the container
  and generated credentials were removed (`DISPOSAL_EXIT=0`). A prior attempt
  against a reused database correctly failed on an existing role and was not
  counted as evidence.
- Revision 36 fixes dataset inspection of nested Hugging Face transport cache
  metadata and adds a regression test. Full AI verification now passes 951
  tests, 112 conditional skips and one existing Starlette/httpx warning; no
  source artifact, candidate flag, cloud resource or provider call changed.
- Revision 37 removes the absolute machine path from local inspection
  manifests. A full 2.1 GB rescan passes with the same 57 blocked artifacts and
  portable manifest digest `70ab9a013f8fa06cc96d8fe839aeba06b486c273c4d332ee29f83ed13e0b53aa`;
  no raw record content or workspace path is persisted.
- Revision 38 reruns the full AI gate after the portable path correction:
  951 passed, 112 conditional skips, one known Starlette/httpx warning, and
  Alembic offline replay through `20260802_0025` all pass.
- Revision 39 performs a fresh read-only cloud reconciliation against
  `vinfast-503003`: Cloud SQL `vfbiz-ai-postgres-dev` is `RUNNABLE` at its
  private address; Artifact Registry contains three immutable `intake-worker`
  digests; Cloud Run has no service or job; the worker subscription has an
  empty `pushConfig` with the bounded DLQ/retry policy; and the three database
  Secret Manager containers have no versions. The current OpenTofu plan is
  `0 add, 0 change, 2 destroy`, limited to stale disabled-worker intake/derived
  bucket IAM members. No plan was applied, no secret was created, and no
  worker/OCR/real-corpus dispatch occurred. The two planned IAM removals and
  the project-scoped Document AI binding remain a named operator/risk gate.
- Revision 40 records the post-wiring AI gate: `verify:ai` passes 954 tests,
  112 conditional skips, Ruff, Pyright and Alembic offline replay through
  `20260802_0025`. This is local provider-factory evidence only; Cloud Run,
  Pub/Sub push, secret versions, OCR dispatch and real-corpus processing remain
  disabled.
- Revision 10 separates immutable worker service deployment from Pub/Sub
  dispatch. `worker_dispatch_enabled=false` removes push delivery without
  destroying the Cloud Run service or evidence, and enabling dispatch before
  service prerequisites now fails validation.
- The AI PostgreSQL secret is pinned to an explicit positive numeric Secret
  Manager version; `latest` is no longer accepted by IaC. The observed
  Document AI processor revision is pinned to
  `pretrained-ocr-v2.1.1-2025-01-31` instead of the nonexistent prior default.
- Required GCP APIs and a prevent-destroy Artifact Registry repository with
  bounded untagged cleanup are represented in IaC. These resources are only
  validated locally; no plan/apply, image publication, push delivery or OCR
  dispatch was performed in revision 10.
- The Pub/Sub service no longer exposes a reconciliation HTTP route. A separate
  Cloud Run Job uses its own service account and restricted numeric-version
  PostgreSQL secret; a default-off Cloud Scheduler trigger can invoke one
  bounded batch every five minutes. Job output and failure receipts are
  content-free and retry policy remains application-owned.
- Revision-17 next action is superseded by Revision 20: independent acceptance
  has now closed the exact-ACL and one-shot bootstrap technical findings.
- Revision 13 adds a fact-free, local-only synthetic knowledge qualification
  packet at active digest
  `50026ed91aa6dfce5b1fa8bebe8aef80e351da3ea151e0892295c8fc6aa595d1`.
  It contains 12 unique page-anchored surfaces across three synthetic document
  modes, with exact source/page hashes, citation lineage, repository-bound
  generator/verifier snapshots and `0700/0600` atomic storage. All human,
  training, upload and release flags are false. The manifest states
  `cloud_ocr_performed=false` and contains no raw PDF, so it proves only local
  qualification/fingerprint plumbing and does not satisfy the reviewed-PDF or
  live Document AI smoke gate above.
- The first delegated implementation attempt failed before work began because
  the provider refresh token was revoked. Root completed the bounded technical
  lane without treating that failure as review or approval; an independent
  dataset-quality recommendation remains required.
- Independent review rejected the first packet for an external-symlink P1 and
  caller-declared authority P2. Both attacks were reproduced and corrected:
  persisted verification now uses `lstat`, an exact directory/file tree,
  single-link regular files and symlink/non-regular rejection; generator and
  verifier source digests are pinned in a candidate-external application
  authority module. The two superseded packets are preserved under the
  rejected knowledge archive rather than being silently deleted.
- The reviewer closed both findings on the first remediation. The complete AI
  suite then exposed a clean-architecture violation because application code
  read the filesystem. The final authority binding was moved back across the
  application/infrastructure boundary and all architecture tests now pass.
  Because the bounded two-cycle review budget is exhausted, the final active
  digest remains pending a later independent acceptance instead of being
  self-approved.
- The initial read-only cloud preflight on 2026-08-01 confirmed project
  `vinfast-503003`/number `81588547131` is active. Cloud Run Admin API remains
  disabled, no Cloud Run service/job can be listed, no Artifact Registry
  repository was observed in `asia-southeast1`, and the only listed secrets are
  the two Langfuse development keys. No private Terraform values existed at
  that checkpoint. Revision 15 adds an ignored local values file containing no
  plaintext credential; no worker image, PostgreSQL role secret, service, push
  dispatch or reconciliation schedule has been deployed.
- A late dataset-quality recommendation reports the prior symlink and
  candidate-authority attacks closed, but cites bundle
  `64d932b7e3ac69595e6e455e74ce560d7faa5ca19da3237ce38334a2c99ee9c6`,
  which is now in the rejected archive. The active architecture-corrected
  bundle remains
  `50026ed91aa6dfce5b1fa8bebe8aef80e351da3ea151e0892295c8fc6aa595d1`.
  The recommendation is retained as useful remediation evidence, not
  misrepresented as acceptance of the active bundle.
- The local private Terraform inputs are now populated with the observed
  development project, billing account and OCR processor identities. A
  refresh-only plan changed no remote resources. Saved plan R14 has SHA-256
  `3c83e52a21814bba3d868d6f8ae7b537126b4a0a0841f401143345889509226b`:
  15 creates, one in-place derived-bucket lifecycle update, one intentional
  legacy Document AI IAM delete, zero replacements and zero public IAM. It has
  not been applied because the canonical packet requires an explicit operator
  disposition for the non-zero delete/retention change and the deployment
  image/database-secret fields remain empty.
- IaC no longer pre-grants derived-bucket read access to an absent reconciler.
  The development lifecycle now applies the seven-day rule only to `LIVE`
  objects and the one-day noncurrent rule only to `ARCHIVED` objects. The
  independent risk review found no P0 or remaining technical P2 but correctly
  retained `VFBIZ-0199-R14-OPERATOR-PACKET-001` as a P1 stop-apply gate.
- A deterministic fact-free PDF pilot packet now exists under the declared
  synthetic quarantine path. It contains one native-text, one image-only and
  one mixed-page PDF, each exactly two pages. Its manifest digest is
  `2fedefbaff8508672b880f893152661b0367a33166ac7bcde33f063fbacfbd1f`;
  every upload, human-adjudication, training and release flag remains false.
  Independent dataset review closed the governance-path and font-rights
  findings, reproduced the DejaVu Sans 2.37 license/digests and found no new
  technical issue. This recommendation does not grant Data Owner upload
  authority or claim OCR quality.
- Worker image R20 builds dependencies with digest-pinned Python 3.14.6 and
  runs them on a digest-pinned Chainguard Python 3.14.6 runtime. It omits uv,
  shell and package manager from runtime and runs as UID/GID 65532.
  Health and content-exclusion checks pass. Its local image ID is
  `sha256:4ba2a570584cfeaf405eb2f925103afc47671a57074d8b3422e46f04064fd63a`;
  SBOM SHA-256 is
  `73936ffc205a2e8f0f4ff6e8e67f2130bd27b67e5f26552b8162fd0c9df6d01b`
  and Grype evidence SHA-256 is
  `3d9c18997861c66f6b2f49d64ac6e2f38d93f7555e50b9d4816cdf4c6d406502`.
  The scan reports zero Critical/High and two Medium findings without a known
  fix in Python mail-client modules that the worker does not import. A full
  isolated Python 3.14.6 test run with test/GCP/fixture groups passes. This
  closes the prior Critical/High technical rejection but remains pending the
  independent residual-risk recommendation; no Artifact Registry image was
  published at that checkpoint.
- The Chainguard base-image signature and SPDX attestation are independently
  verified by Cosign against the official public-registry GitHub workflow and
  Sigstore transparency log. Signature evidence SHA-256 is
  `f1c56af0a62f560a1abf453a4f3affdc8dac24a3d781f0bde37a10be24a07b71`;
  attestation evidence SHA-256 is
  `b4fb8d629eb15ea9768cc0c4fcfde374d613c54f9798b1cb1bed1ddcdb87707e`.
- The destructive R14 proposal was superseded, not applied. IaC now keeps the
  imported broad Document AI grant and seven-day soft-delete policy unchanged
  during foundation-only rollout. Saved plan R16 SHA-256
  `f2b22c3ae5d4083102c82f25978a5bcfc19f5148984cfa432c7a888123544983`
  contained exactly 15 creates, 25 no-ops, zero updates/deletes/replacements
  and zero public IAM. It applied exactly: Artifact Registry, required APIs,
  three unbound custom roles and two unbound service accounts were added.
- Post-apply plan SHA-256
  `94d001436b76201500f93ad0e4ac2af89ef7b61877e9f2afa17e9adf2c413689`
  reports `No changes`. Cloud Run worker/job, Pub/Sub push and scheduler remain
  absent/disabled; IAM and bucket retention were not changed.
- R20 is published only to private Artifact Registry at
  `asia-southeast1-docker.pkg.dev/vinfast-503003/vfbiz-ai-workers-dev/intake-worker@sha256:4ba2a570584cfeaf405eb2f925103afc47671a57074d8b3422e46f04064fd63a`.
  Remote OCI inspection reproduces the local digest and retains the amd64
  provenance-attestation manifest. Artifact Registry reports SLSA level
  `unknown`, so publication is supply-chain staging evidence, not deployment
  or release authority.
- The complete deterministic AI gate passes 879 tests with 104 explicit
  conditional skips. Migration `20260802_0024` now creates distinct NOLOGIN,
  non-privileged submitter and reconciler capabilities with disjoint direct
  table grants. All 225 PostgreSQL integration tests pass from an empty
  PostgreSQL 17/pgvector database through the new head; the disposable
  container was removed.
- A fail-closed operator command now preflights migration head and role
  properties before it can rotate two distinct login identities and publish
  two numeric Secret Manager versions. It is dry-run by default and never
  prints credentials. No production login or secret version was created.
- A fresh independent dataset-quality review now accepts the exact active
  architecture-correct synthetic knowledge packet for restricted technical
  qualification only. Subject digest
  `50026ed91aa6dfce5b1fa8bebe8aef80e351da3ea151e0892295c8fc6aa595d1`
  binds generator
  `2d98740d40e5f91610020f6e1b4e795fe31e006ed75bf1efb54cc6962e564856`,
  verifier
  `c5b7ecba39ca52140a303b462c282c290eb870b98f5394fe6a7dbc8847c8bd45`,
  external authority
  `67f8b7fe685fda51e131206ca916f60ffa4042d8cd5732b40453e7a07d0842ba`
  and infrastructure store
  `71f47d3442ef4f0089178a1cb44c36702d72b9fce57dbcd69359e50922a70803`.
  No P0/P1/P2 was found; upload, training, release and active-retriever flags
  remain false.

## Deployment operator packet

The next cloud action is permitted only after one packet binds all of these
values without plaintext credentials:

- project `vinfast-503003`, project number `81588547131`, region
  `asia-southeast1` and the existing billing-account/processor identifiers;
- one immutable Artifact Registry worker image URI ending in
  `@sha256:<64-hex>`;
- two different PostgreSQL login roles and two different Secret Manager IDs,
  each pinned to a positive numeric version, for intake and reconciliation;
- one reviewed synthetic PDF SHA-256 mapped to its independently observed page
  count from 1 through 500; the local knowledge JSON packet is not a PDF and
  cannot satisfy this field;
- a named development risk disposition acknowledging that the disjoint
  Document AI submit/read custom permissions remain project-scoped;
- saved OpenTofu plan digest, explicit zero replacement/destruction result,
  rollback image digest and dispatch/scheduler switches initially `false`.

Until that packet exists, the correct executable state is service absent,
dispatch disabled, schedule disabled and real-corpus upload prohibited. The
operator must enable/apply Cloud Run and Artifact Registry through the reviewed
IaC plan rather than an ad-hoc console mutation.

## Evidence

- [x] Focused unit/security tests — `backend/ai/tests/unit/datasets/test_object_store_security.py`,
  `backend/ai/tests/unit/knowledge/test_gcp_cloud_ingestion.py`,
  `backend/ai/tests/unit/datasets/test_managed_source_intake.py`,
  `backend/ai/tests/unit/knowledge/test_release_domain.py` pass.
- [x] Synthetic GCP smoke — object
  `gs://vinfast-503003-intake-dev/synthetic-smoke/20260730/acfdf11e99550baa96057c8028ac0190ac01077c8d8a8e2a75b136202f34f485.jsonl`
  was uploaded with SHA-256
  `acfdf11e99550baa96057c8028ac0190ac01077c8d8a8e2a75b136202f34f485`,
  generation `1785394873290884`, CRC32C `5lnARg==`, size `1563`, metadata
  `authority_class=synthetic-smoke-only`; the object was then removed and
  verification returned `404 not found`.
- [x] `npm run contracts:lint` — passed with 38 contracts, 67 dataset vectors,
  8 isolated operations and 24 workforce capabilities.
- [x] `npm run verify:ai` — latest run passed with 760 tests and 100 skipped;
  Ruff, Pyright and Alembic dry-run through `20260801_0023` passed.
- [x] `npm run verify:ai:integration` — passed against temporary local
  PostgreSQL/pgvector integration database, including durable reservation,
  concurrent claim exclusion, stale-fence rejection, deadline-failure
  persistence and restart/replay evidence; container was stopped afterward.
- [x] `npm run governance:check` — passed after regenerating the 93-document
  index; dependency-risk, authorization, work references and agent governance
  are current.
- [x] OpenTofu provider validation/import/reconciliation — installed OpenTofu
  `1.12.5`, initialized the GCS backend, imported existing GCP resources,
  applied the reviewed reconciliation plan and confirmed a post-apply
  `No changes` plan.
- [x] Worker Document AI IAM — added `roles/documentai.apiUser` to the worker
  service account, verified the binding with GCP IAM policy and confirmed a
  post-recovery OpenTofu `No changes` plan.
- [x] Independent reviewer recommendations — infra and risk reviewers returned
  findings; infra readiness is limited to the next synthetic worker/smoke step,
  and risk readiness excludes real corpus, Dataset Release, Golden, staging and
  public activation.
- [x] Repository verification — `npm run contracts:lint` passed with 38
  registered AI contracts and 67 dataset vectors; `npm run verify:ai` passed
  with 741 tests and 98 conditional skips; `npm run verify:ai:integration`
  passed on a clean temporary PostgreSQL/pgvector database; governance passed.
- [x] API verification — `npm run verify:api` passed lint, typecheck, 387 unit
  tests, 67 E2E tests, Prisma validation and build.
- [x] Second independent correctness/DB/risk review — completed read-only;
  deterministic findings were remediated and activation-only residuals remain
  blocked rather than accepted by an agent.
- [ ] Authenticated push/Document AI live smoke — blocked on the exact synthetic
  manifest, private operator values and named IAM risk disposition above.
- [x] Document AI-only local handoff and release-ineligible candidate retirement
  checks — 30 focused tests passed, including exact output lineage, low-quality
  review routing, incomplete-page, CRC mismatch, prefix escape and non-ready
  receipt negatives.
- [x] Durable reconciliation verification — focused tests passed; the full AI
  gate passed with 755 tests and 100 conditional skips; PostgreSQL integration
  passed on a clean disposable pgvector/PostgreSQL 17 database through migration
  `20260801_0023`, including restart, replay, concurrent claim exclusion,
  canonical float parity, missing/extra key rejection, forged observation,
  conflicting evidence, retry/backoff and immutable-table checks. The disposable
  container was removed.
- [x] IaC static validation — `tofu fmt -check -recursive` and `tofu validate`
  passed after adding bounded derived-output retention and explicit worker
  memory limits. No apply was performed without a reviewed saved plan.
- [x] Cross-system deterministic gates — `npm run contracts:lint`,
  `npm run governance:check` and `git diff --check` passed after the durable
  reconciliation change.
- [x] Revision-10 IaC validation — OpenTofu format check and validation passed
  for numeric secret version pinning, separate service/dispatch switches,
  managed API enablement, exact OCR revision and the immutable worker image
  repository. No cloud mutation was performed.
- [x] Revision-10 workload separation — focused Ruff, Pyright and 16 unit tests
  passed for Pub/Sub-only HTTP intake and the sanitized reconciliation job
  entrypoint; OpenTofu validated the distinct reconciler/scheduler identities
  and default-off schedule.
- [x] Revision-10 full deterministic gates — `verify:ai` passed 798 tests,
  `verify:ai:integration` passed 215 tests on a disposable PostgreSQL 17 +
  pgvector database through migration `0023`, `verify:api` passed 405 unit and
  67 E2E tests, `verify:apps`, contracts and governance all passed. The
  disposable database was stopped and removed.
- [x] Revision-11 least-privilege delta — the broad Document AI role was
  replaced by disjoint submit-only and operation-read-only custom roles; the
  reconciler output role proves exact `objects.get/list` permissions through a
  versioned IAM contract. Terraform now rejects reused worker/reconciler DB
  secret IDs, and Artifact Registry cleanup is dry-run. OpenTofu validation,
  Ruff and 32 focused architecture/knowledge tests passed; no plan, apply,
  secret creation, image publication or provider dispatch occurred.
- [x] Revision-11 independent re-review — risk review closed the three prior
  code findings and correctness review closed the GCS-list finding. Correctness
  retained one bounded deployment P1 for project-scoped Document AI custom
  permissions; it is documented rather than incorrectly represented as
  processor-scoped. Both reviews prohibit apply/dispatch until the actual-value
  saved plan, separate DB principals, reviewed synthetic manifest, exact image
  digest and named residual-risk disposition exist.
- [x] Revision-11 local checkpoint — the scoped code/contracts/IaC/docs diff is
  bound to SHA-256
  `0f83751e69678525c6606607457eb79fb7c5638321c35fd1eb52ea968484f267`.
  `verify:ai` passed 801 tests with 101 conditional skips; contracts,
  governance, OpenTofu validation and `git diff --check` passed. The existing
  Starlette/httpx compatibility deprecation remains a non-release warning and
  no cloud/provider action occurred.
- [x] Revision-13 synthetic knowledge qualification — Ruff, Pyright and 12
  focused knowledge/contamination tests pass. The exact restricted packet has
  12/12 citation-complete surfaces and zero forbidden-content matches; no raw
  PDF, provider call, OCR claim, embedding, upload or release occurred.
- [x] Revision-13 full deterministic gate — `verify:ai` passed 859 tests with
  101 explicit conditional skips; contracts, governance, documentation index,
  packet checksums/permissions and `git diff --check` pass. The existing
  Starlette/httpx compatibility warning remains non-blocking.
- [x] Revision-13 independent dataset-quality acceptance — prior P1/P2 findings
  were closed on the first remediation, and the final architecture-corrected
  active digest has now received the later independent pass recorded below.
- [x] Revision-22 active synthetic packet acceptance — exact-tree/checksum,
  lstat/symlink/hardlink/FIFO/permission, external-authority, 12/12 citation
  lineage, fact-free/PII/secret/injection, contamination and retriever-isolation
  gates passed. Twenty-three candidate/contamination/boundary tests and 17
  retrieval-service tests passed. Recommendation is restricted technical
  acceptance only and grants no Data or Release decision.
- [x] Revision-14 read-only cloud preflight — project identity was confirmed;
  Cloud Run, Artifact Registry, worker/reconciler database secrets and private
  deployment prerequisites were absent, so no deployment or provider dispatch
  was falsely claimed. Revision 15's ignored local values do not change that
  cloud state.
- [x] Revision-15 synthetic PDF packet — three two-page fact-free PDFs are
  deterministic, content-addressed, structurally safe and independently
  reviewed. Exact-tree, permission, symlink, hardlink and altered-font
  regression tests pass; all authority flags remain fail-closed.
- [x] Revision-15 saved-plan review — refresh-only changed no remote resources;
  saved plan R14 has zero replacement/public IAM but one intentional IAM delete
  and one retention update. Independent risk review retained the operator
  authorization P1, so no apply occurred.
- [x] Revision-15 worker supply-chain evidence — digest-pinned multi-stage,
  distroless Linux/amd64 image runs non-root, passes health and excludes uv,
  shell, package manager, tests, local data and gcloud credentials. SBOM/CVE
  evidence is sealed locally. Historical R19 was rejected rather than published
  because its scan contained unresolved Critical/High findings; R20 supersedes
  it at revision 16.
- [x] Revision-15 full deterministic gate — its checkpoint passed 873 tests
  with 101 conditional skips; contracts, focused architecture/fixture tests,
  OpenTofu formatting/validation and governance remain required at handoff.
- [x] Revision-16 hardened worker candidate — R20 is digest-pinned, non-root,
  shell-less and package-manager-free; health and exclusion checks pass. Grype
  reports zero Critical/High and two Medium findings without a known fix. The
  full suite also passes on isolated CPython 3.14.6 with all declared optional
  test groups. The first independent residual-risk attempt failed from reviewer
  quota and is not acceptance; a replacement read-only review is pending.
- [x] Revision-16 foundation apply — reviewed saved plan R16 applied 15 creates,
  zero changes and zero destroys; post-apply plan is clean. It created no
  service, dispatch, schedule, secret binding, OCR request or dataset.
- [x] Revision-16 private image publication — remote digest exactly matches the
  local R20 digest, base signature/SPDX attestation verify through Sigstore, and
  no Cloud Run deployment occurred. Artifact Registry's unknown SLSA level is
  retained as an explicit residual supply-chain gap.
- [x] Revision-16 independent supply-chain review — the replacement read-only
  reviewer reproduced the remote digest, non-root/shell-less runtime, private
  repository, zero Critical/High scan, base signature/SPDX verification and
  clean foundation plan. It found no new P0/P1 for private publication and
  retained the Document AI project-scope, data-activation and final-image
  provenance gates for deployment.
- [x] Revision-17 database capability split — independent review reproduced
  two P1 defects in the first draft: the reconciler could not take its required
  row lock, and a pre-existing contaminated capability role was adopted. The
  remediation grants only column-level `UPDATE(id)` for the lock, rejects every
  role-name collision transactionally, checks broader capability/login
  memberships during operator preflight and exercises actual repository paths
  under both roles plus forbidden DML. The focused role test, contaminated-role
  collision test, full PostgreSQL integration profile and 879-test AI gate pass
  on clean disposable databases. The second review closed those three findings
  and found one new operator-preflight P1: inbound actor membership and exact
  live ACL drift were not checked. The final remediation now compares both
  membership directions and the exact table/column ACL allowlist before secret
  creation; a real PostgreSQL regression injects an unexpected actor and
  reconciler DELETE grant and proves both are rejected. The two-cycle review
  budget is exhausted, so this last delta remains pending later independent
  acceptance rather than being self-approved. No Cloud SQL login or secret
  value was created.
- [x] Revision-18 private database foundation plan — the default-off saved plan
  digest `2aa3f7d03aeb3ffee030703fe91d54ebd1f0eef98967f2a8fdd88db3152f777b`
  contains 40 no-ops and no change. The explicitly enabled saved plan digest
  `2588dd29c52bc5b8eb09fc694be0792fecf1d57e43a313e9d8bbd1105a9cca86`
  contains exactly 13 creates, 40 no-ops, zero update/delete/replace and creates
  no Cloud Run workload, scheduler, push dispatch, SQL user, secret payload or
  public IAM. It provisions only a protected private PostgreSQL 17 development
  foundation, dedicated Direct VPC path and three empty protected secret
  containers. Independent risk review found no P0/P1 and retained one P2:
  automatic secret replication must receive a named Security/Data residency
  disposition before secret version 1. The reviewed plan was not applied;
  applying it remains an explicit Cloud Operator decision because it starts a
  billable shared-core instance with Zonal/daily-backup recovery tradeoffs.
- [x] Revision-18 deterministic checks — seven focused IaC architecture tests,
  OpenTofu format/validation, plan-policy queries, `contracts:lint`,
  `governance:check` and `verify:ai` all pass. The AI gate observed 881 passed,
  104 conditional skips and the existing Starlette/httpx compatibility warning.
- [x] Revision-19 final foundation plan — later bootstrap source changes do not
  enter the foundation-only plan. Default-off plan SHA-256
  `f0b3b840e607f3ffe0931fbd3ebaf2e27731008d96474e03f54a6f24901aba95`
  remains 40 no-ops. Foundation plan SHA-256
  `40d87c297960deb976e0c9355f85b4c78571c141bcf352ba5261e97bca469c5c`
  remains exactly 13 creates and 40 no-ops with no update, replacement,
  deletion, bootstrap IAM/job, workload, SQL user, secret payload or public
  principal. Independent risk review reproduced both plans; no apply occurred.
- [x] Revision-19 one-shot bootstrap implementation — migration
  `20260802_0025` stores one immutable epoch, claim UUID, external authority
  digest and fencing token before external writes. Concurrent/replayed runs are
  rejected, terminal evidence cannot be mutated or deleted, and downgrade is
  refused for reserved, completed and failed states. Password rotation and the
  completed evidence transition now share one PostgreSQL transaction. A thrown
  commit reconnects and reconciles the exact claim before any secret version is
  disabled; an unknown outcome stays indeterminate and forbids retry/cleanup.
  Failure cleanup attempts every created version and preserves the primary
  error with only a content-free failure code.
- [x] Revision-19 dedicated bootstrap image candidate — operator code is absent
  from the OCR worker and lives in a separate shell-less, non-root Linux/amd64
  image. Local R3 ID is
  `sha256:393310ee240a516f516951eebc126f64227bdd5cfbef776df919ce5be8cd53fb`;
  it contains Alembic head `0025`, fails closed without the apply witness and
  has zero Critical/High plus two unpatched Medium Python mail-client findings.
  SBOM SHA-256 is
  `f2d5d2252cfce9fe3f51c81d1bf0ca92ead1913d503c048d4fbe5144f01cdd72`;
  scan SHA-256 is
  `b1c283fdc9e1e5e3898c4d6adf568ad32fa06371a704a25b3e88bc6e91f993ea`.
  This image remains local and is not an Artifact Registry or deployment
  identity.
- [x] Revision-19 bootstrap rejection — the independent review found and
  bounded two P1 defects: non-atomic completion and replay after downgrade. Both
  were remediated and exercised, but the then-current two-cycle review budget
  ended before that delta could be accepted. A later fresh reviewer in Revision
  20 performed the required independent acceptance.
- [x] Revision-19 database gate — the complete PostgreSQL 17/pgvector profile
  passed all 231 then-collected integration/evidence cases through Alembic head
  `0025` on a fresh disposable database; the container was removed.
- [x] Revision-19 repository gate — documentation generation,
  `contracts:lint`, `governance:check`, Ruff, Pyright and `verify:ai` pass.
  That AI run observed 891 passed, 109 conditional skips and the existing
  Starlette/httpx compatibility warning. OpenTofu format/validation and
  `git diff --check` also pass, with no disposable bootstrap test container
  left behind.
- [x] Revision-20 independent bootstrap acceptance — a fresh read-only reviewer
  reproduced three additional P1 failures before acceptance: invalid
  parameterized `ALTER ROLE ... PASSWORD`, incomplete effective-authorization
  preflight and a non-locking ambiguous-commit reconciliation race. The
  remediation uses Psycopg identifier/literal composition for PostgreSQL
  utility SQL; validates login attributes, both membership directions plus
  `ADMIN`/`INHERIT`/`SET` options, and exact capability/login/`PUBLIC` table and
  column ACLs; and reconciles through a bounded `SELECT ... FOR UPDATE`.
  Regression probes cover `ADMIN OPTION`, direct-login `DELETE`, `PUBLIC
  DELETE`, real password rotation and an in-flight completion transaction.
  The reviewer observed 22 focused non-database and nine fresh PostgreSQL 17
  tests passing, closed all three fingerprints and reported no P0–P2. This is
  technical acceptance only, not activation or release authority.
- [x] Revision-20 full gates — the complete fresh PostgreSQL 17/pgvector profile
  passes all 234 collected integration/evidence tests through Alembic head
  `0025`. The repository gate passes Ruff, Pyright and 891 tests with 112
  conditional skips; the only warning remains the existing Starlette/httpx
  compatibility warning. The disposable database was removed.
- [x] Revision-21 cloud drift preflight — the current read-only default-off
  saved plan has
  SHA-256
  `2a2576647409641da7fe8f53af0cc565fd5ceed219ea241d1eb6ba118a564f61`
  and contains exactly 40 no-ops with no create, update, replacement or delete.
  No provider inference or billable resource creation occurred.
- [x] Revision-21 regional secret replication — all three proposed database
  secret containers now have exactly one user-managed replica in
  `asia-southeast1`; automatic multi-region replication is absent. Independent
  risk review reproduced both saved plans, passed eight focused architecture
  tests plus OpenTofu validation and closed the former automatic-replication P2
  with no new P0–P2. This is technical residency enforcement only and does not
  replace a named Data/Privacy disposition.
- [ ] Revision-21 activation authority — foundation apply, administrator secret
  version, private bootstrap-image publication, bootstrap IAM/job, worker
  deployment, synthetic OCR dispatch and all real-corpus processing remain
  disabled. The current saved foundation plan has SHA-256
  `da62dcc82b2a31dd71124f3c8c8ea97ee8869cdafbbc5f8a9f5348de1ad9bb70`
  and contains exactly 13 creates plus 40 no-ops, with zero
  update/delete/replace, Cloud Run workload, SQL user, secret version or public
  principal. The exact next action is an explicit Cloud Operator decision on
  this plan and its shared-core cost/Zonal recovery tradeoff. Data/Privacy must
  accept or reject the exact Singapore-only replication requirement; Data
  Owner must bind the exact synthetic pilot digest/page count and retention;
  Security/Risk must disposition the project-scoped Document AI permission and
  final-image provenance before any activation plan is produced.
- [x] Revision-41 continuation read-only cloud/IaC preflight — `tofu validate`
  passed. The current saved plan at `/tmp/vfbiz-continuation.plan` contains
  exactly `0 add, 0 change, 2 destroy`; both proposed destroys are stale
  conditional worker bucket IAM members left in state while the worker remains
  disabled (`worker_service_enabled=false`). No apply was run. GCP confirms no
  Cloud Run service/job, Pub/Sub authenticated push, or runtime secret version;
  the worker subscription remains pull-only with five-attempt DLQ and bounded
  retry. This supersedes any older claim that the current plan is zero-change;
  the two stale IAM entries must be reconciled in a separately reviewed IaC
  correction before activation.
- [x] Revision-42 clean PostgreSQL integration run — a newly created disposable
  PostgreSQL 17/pgvector container on `127.0.0.1:55433` upgraded through
  Alembic head `20260802_0025` and the configured integration command exited
  successfully with all 234 collected cases passing. A later rerun against
  the same database correctly exposed six contamination failures (existing
  governed rows and cluster-level Document AI roles); the old container was
  not reused for acceptance and both disposable containers created for this
  check were stopped. The integration precondition is therefore an isolated
  fresh database/cluster per run, not a reusable stateful database.
- [x] Revision-43 bounded ingestion integrity correction — a 412 rewrite replay
  now reads the exact staged generation with generation/metageneration
  preconditions and recomputes SHA-256, byte size and CRC32C before OCR submit.
  Valid and forged pre-existing destination regressions pass; the focused
  worker/reconciler/IAM suite is green. The runtime now passes the configured
  source-byte cap to the GCS verifier. No cloud write, secret version, OCR or
  corpus upload occurred.
- [ ] Revision-43 activation risks remain — `storage.objects.list` is bucket
  scoped and cannot be safely narrowed by the current object-prefix IAM
  condition; the reconciler needs a dedicated output bucket/managed-folder
  boundary before activation. The current live plan still has two stale IAM
  destroys, and project-scoped Document AI access, image provenance/scanning,
  cost hard-stop, synthetic authority and retention decisions remain open.
- [x] Revision-44 media-read hardening — Document AI output downloads now pin
  both generation and metageneration in addition to the metadata recheck;
  focused GCP ingestion tests and Ruff remain green. Full `verify:ai` reports
  956 passed and 112 conditional skips, with Alembic offline generation through
  `20260802_0025`. No provider request or cloud mutation occurred.
- [x] Revision-45 fresh PostgreSQL integration — a new disposable
  `pgvector/pg17` container on `127.0.0.1:55435` upgraded through
  `20260802_0025`; the configured integration/evidence profile exited 0, then
  the container was stopped. This is an isolated-run acceptance precondition;
  no shared database or GCP SQL state was reused.
- [x] Revision-46 dedicated OCR-output boundary — the worker now stages input
  objects in `derived-dev`, while Document AI writes to a separate
  `ocr-output-dev` bucket. The reconciler reads/lists only that dedicated
  bucket, removing the unsafe prefix-scoped `storage.objects.list` assumption;
  runtime settings require distinct staging/output buckets and reject either
  bucket being reused as an input bucket. Focused IAM, settings, GCP object
  integrity and worker/reconciler tests pass; OpenTofu format and validation
  pass. No bucket was created and no workload was enabled.
- [ ] Revision-46 cloud reconciliation — a fresh read-only plan saved at
  `/tmp/vfbiz-0199-r46-default.tfplan` (SHA-256
  `7ae6df07db68d897f82cf7a533e621e8792469837d6b16915b250d036bb18f6d`) reports
  `0 add, 1 change, 2 destroy`: only the reconciler role description changes
  and two stale disabled-worker IAM entries would be removed. It does not
  create the OCR-output bucket because both workloads remain disabled. The
  remote Terraform state currently has a stale lock; no force-unlock or apply
  was performed. A Cloud/IaC operator must reconcile lock ownership and review
  the stale IAM removal before any plan can be applied.
- [x] Revision-46 independent ingestion/risk review — reviewers reproduced the
  dedicated bucket boundary, 40 focused GCP/IAM/object-store tests and the
  settings split-validator with no new P0/P1. They confirmed the live OCR
  output bucket, Cloud Run workloads, Pub/Sub push and runtime secret versions
  are absent. Activation remains gated on state-lock reconciliation, workload
  identities/secrets, Document AI permission/provenance, cost hard-stop and
  synthetic/data authority decisions.
- [x] Revision-47 explicit output-bucket retention and composition guard — the
  dedicated bucket is now controlled by an explicit, default-off
  `ocr_output_bucket_enabled` flag rather than workload count. Workload
  lifecycle preconditions require that flag; reconciler IAM cannot index the
  bucket unless both the service and flag are enabled. This keeps the bucket
  retained across later disable/rollback cycles and fails closed if an
  operator tries to enable a workload without it. The runtime composition test
  proves staging input, OCR output, reader and worker receipt all receive the
  intended separate bucket values. The focused IAM, ingestion and object-store
  suite passes 42 tests. Retention documentation now matches the staging/output
  split and soft-delete policy.
- [ ] Revision-47 current default-off plan — after the explicit flag change,
  a lock-protected read-only plan `/tmp/vfbiz-0199-r47-locked.tfplan` (SHA-256
  `e98e9af9358053f6bad82892570e77797bed6a490690e147a30b0a5328d8bcb8`) reports
  `0 add, 1 change, 2 destroy`: the custom role description update and the two
  stale disabled-worker IAM bindings. It does not create the OCR-output bucket
  while the flag and workloads remain disabled. No apply occurred. The stale
  IAM cleanup and any future explicit flag enablement require a reviewed
  Cloud/IaC operator plan; protected bucket disablement is intentionally
  fail-closed rather than silently destructive. The plan acquired and released
  the remote state lock normally; no force-unlock was used.
- [x] Revision-50 activation-packet gate — Terraform now requires six
  content-free packet fields before either Cloud Run workload can become
  lifecycle-ready: authority digest/generation, saved-plan digest, rollback
  image digest and named Document AI risk-disposition digest/reference. All
  fields are empty by default, so no resource was enabled. OpenTofu
  format/validate and the focused GCP/IAM suite pass.
- [x] Revision-50 read-only cloud confirmation — `asia-southeast1` currently
  has no Cloud Run service or job; `vinfast-document-worker-dev` has an empty
  `pushConfig`, five-attempt DLQ and 10–600 second retry; buckets are limited
  to intake, derived, evidence and Terraform state, with no OCR-output bucket.
  No cloud mutation, corpus upload or Document AI request occurred.

### implementation — 2026-08-03 (candidate materialization boundary)

The Document AI path now has a concrete, content-addressed local candidate sink
and a post-reconciliation worker. The worker accepts only a succeeded,
generation-bound receipt, then runs scan/review, deterministic chunking and
embedding before publishing a manifest-last candidate artifact. Source
generation conflicts, tombstone high-water marks, replay divergence, malformed
digests, path traversal and permission regressions fail closed. Replaying an
identical manifest is idempotent and no active release pointer is modified.
Focused materialization tests (9) and AI full verification pass. This remains
developer candidate evidence; cloud deployment and first-party source approval
are still absent.

### preflight — 2026-08-03 (read-only cloud state)

The active operator is authenticated to `vinfast-503003`. Read-only discovery
found four private Singapore buckets (intake, derived, evidence and Terraform
state), no Cloud Run service/job and no Vertex custom job, endpoint or custom
model in the checked regions. OpenTofu validation passed and a refresh-only plan
completed without applying changes, but it observed remote drift. The current
default plan is **not** an activation plan: `0 add, 1 change, 2 destroy`; the
two destroys are stale disabled-worker IAM bindings. No apply, upload, OCR,
Vertex call or secret-version creation was performed. The separate
`vinfast-staging-503003` project is not accessible to the active identity.
Activation therefore remains stopped until a Cloud Operator supplies a
content-free packet and a reviewed zero-destroy plan.
