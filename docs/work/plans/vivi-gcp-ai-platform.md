---
id: plan-vivi-gcp-ai-platform
title: ExecPlan GCP AI Platform, ViVi text voice and evidence-gated tuning
status: active
owner_role: engineering-lead
scope: cross-system
when_to_read:
  - VFBIZ-0199
  - VFBIZ-0200
  - VFBIZ-0201
  - VFBIZ-0202
tags:
  - gcp
  - knowledge-ingestion
  - vivi-voice
  - evaluation
  - fine-tuning
revision: 25
review_date: 2026-08-30
supersedes: []
---

# Purpose

Deliver a text-first VinFast Customer Assistant staging candidate backed by
bounded GCP ingestion, governed RAG, measurable ViVi text voice and independent
evaluation. Fine-tuning remains conditional evidence work and never substitutes
for knowledge freshness, citation, ACL or human release authority.

## Boundaries

- Public Chat API remains disabled until VFBIZ-0195.
- Raw VinFast content remains outside Git and cannot enter Golden or training.
- Development quarantine/OCR does not create Content, Legal, Data, Brand or
  Release approval.
- Provider SDKs and GCP resource names remain infrastructure configuration, not
  domain concepts.
- Audio ASR/TTS, RFT, continuous tuning, GPU and Provisioned Throughput are
  outside this plan.

## Progress

- [x] GCP development project, private buckets, Pub/Sub, worker identity,
  Document AI OCR processor and monthly budget alert exist.
- [ ] VFBIZ-0199: codify and verify GCP ingestion. Existing resources are now
  imported into OpenTofu remote state. Saved foundation plan R14 is reviewed
  but deliberately unapplied because it contains one intentional IAM delete,
  one retention change and incomplete deployment inputs. Submission,
  reconciliation and the reviewed synthetic PDF gate pass locally. Worker
  image R20 has zero Critical/High findings and independent review found no new
  P0/P1 for private publication. Synthetic live OCR and deployment remain
  blocked on the separate activation gates. Revision 18 now has an independently
  reviewed, default-off private PostgreSQL foundation plan; it remains
  unapplied pending an explicit Cloud Operator cost/recovery decision. Revision
  20 independently accepts the one-shot database bootstrap implementation after
  real PostgreSQL verification of exact effective authorization, password
  rotation, ambiguous-commit locking, replay and downgrade safety. No secret
  version, bootstrap job, worker or OCR dispatch was activated. Revision 21
  further constrains all three proposed database secret containers to one
  user-managed `asia-southeast1` replica. Independent risk review closed the
  former automatic-replication P2 technically; Cloud Operator and named
  Data/Privacy activation decisions remain outstanding. Revision 47 now
  separates worker staging (`derived-dev`) from the dedicated OCR output
  bucket (`ocr-output-dev`), with an explicit default-off retention flag and
  runtime composition tests; no bucket or workload was activated.
  Revision 50 adds a content-free activation-packet gate: workload readiness
  now also requires the packet's exact GCS generation/digest, reviewed
  saved-plan digest, rollback image digest and named Document AI
  risk-disposition digest/reference. All fields remain empty by default, so
  the current foundation is still disabled.
  Revision 51 adds an independent canonical packet validator under
  `backend/ai/scripts`; it produces digest-only output and is required before
  Terraform variables are populated. No packet, apply or cloud mutation was
  created by this change.
  Revision 52 adds the provider-neutral downstream Document AI materialization
  boundary. It routes provider-review or scan-rejected pages to review, runs
  chunking and embedding only for passed pages, verifies embedding lineage
  before one atomic candidate sink call, and never activates a retriever or
  public Chat. Focused and full AI checks are green; no cloud call or real
  corpus was used. Revisions 53–55 close partial-document readiness, align the
  ingestion documentation and complete the API/apps verification pass. Revisions
  56–57 align all unit and PostgreSQL submission-ledger output fixtures with the
  dedicated OCR-output bucket while retaining `derived-dev` solely for staging;
  this is test-boundary evidence only and does not enable a workload. Live
  stale IAM/Document AI permission review remains an explicit activation gate.
  Independent correctness/risk scans found no remaining P0–P2 fixture drift;
  the direct focused command passed 46 tests with 8 expected DB skips, while
  broader reviewer scopes also passed. No cloud mutation occurred.
  Revision 59 strengthens candidate receipts with source generation/
  metageneration and every processor, scanner, policy, chunker and embedding
  revision, so downstream release checks do not infer lineage from filenames or
  filesystem timestamps.

## Capability readiness matrix

The matrix below is the release-facing status authority for the six stable AI
capabilities. “Authority-accepted” distinguishes technical verification from a
named human decision; “cloud-deployed” is false unless a live workload and
post-deploy evidence exist.

| Capability | Implemented | Runtime-wired | DB-tested | Cloud-deployed | Authority-accepted | Release-active |
| --- | --- | --- | --- | --- | --- | --- |
| `knowledge` | yes | local + GCP intake/reconcile; materializer boundary explicit | yes | no | synthetic technical only | no |
| `datasets` | yes | local intake/registry | yes | no | candidate only | no |
| `evaluation` | yes | planner/runner/sealer | yes | no | `public-diagnostic` only | no |
| `inference` | yes | release-bound provider factory | yes | no live provider | no bake-off decision | no |
| `assistant` | yes | local governed graph | yes | no | no staging release | no |
| `governance` | yes | release resolver + kill switch | yes | no | no VinFast witness | no |

The matrix is intentionally conservative: a green local test or provider
catalog lookup cannot promote a capability to cloud-deployed, authority-
accepted or release-active. Current evidence is pinned in VFBIZ-0199,
VFBIZ-0192, VFBIZ-0200, VFBIZ-0201 and VFBIZ-0211.
  Revision 53 prevents partial-document false readiness: one review-required
  page keeps the full extraction review-required, and scanner/policy/chunker/
  embedding revisions are pinned before any candidate write. No provider call,
  cloud mutation or source approval was created.
  Revision 54 aligns the knowledge-ingestion documentation with that boundary;
  it does not change cloud state or release eligibility.
- [ ] VFBIZ-0200: bind ViVi text voice candidate and evaluation authority.
  Human routing for the voice packet goes through Product Owner, Design Lead,
  VinFast Content/Brand SME, Legal Owner, Data/Privacy Owner and Release
  Owner; the candidate itself remains blocked until those reviews land.
- [ ] VFBIZ-0136/0193: obtain genuine source and Dataset Release authority.
- [ ] VFBIZ-0196/0139: 1,000 held-out Golden candidate cases now exist in one
  content-addressed packet and passed scoped technical review. Golden Release
  remains blocked on complete cross-product contamination evidence and genuine
  human adjudication (currently 0/1,000).
- [ ] VFBIZ-0201: execute Vertex embedding/generation bake-off.
  The provider-neutral retrieval summary now fails closed when evidence or
  refusal slices are empty, and the Vietnamese coverage validator requires
  both outcome classes before any live bake-off can be considered. A frozen
  retrieval bake-off manifest now additionally binds ordered held-out cases to
  one source release, index generation, evaluator revision and canonical suite
  digest. A separate `RetrievalSuiteAuthority` validator now requires an
  external provenance/held-out authority record before the suite can release;
  this is local integrity evidence, not a live provider result.
- [ ] VFBIZ-0202: run tuning only if a stable non-factual gap remains.
- [ ] VFBIZ-0194/0197/0195: factual staging, supply-chain and public activation.
- [ ] VFBIZ-0169: semantic routing remains blocked on immutable VI/EN routing
  slice evidence. The deterministic keyword fallback is now capped at `0.6`
  and cannot bypass a release-bound semantic classifier; this is local policy
  hardening only and does not activate classifier routing.

## Decisions

- Region is `asia-southeast1`; existing resources are imported, not recreated.
- Synthetic fixtures prove cloud execution before any real corpus upload.
- Intake, derived-staging, dedicated OCR-output and evidence buckets are
  development trust-zone resources, not a Dataset Release. The reconciler's
  object-list permission is bounded by the dedicated OCR-output bucket because
  GCS IAM Conditions cannot safely constrain `storage.objects.list` to a
  prefix. The output bucket is default-off and must be explicitly retained
  through any workload disable/rollback cycle; no adapter may treat this
  development layout as production approval.
- Enterprise Document OCR uses asynchronous batches with at most 500 pages.
- `gemini-embedding-001` at 768 dimensions is the first candidate; 1536 is a
  bake-off candidate.
- Official Google lifecycle and model-card evidence refreshed on 2026-08-02
  now lists `gemini-3.5-flash` and `gemini-3.5-flash-lite` as GA. The former is
  available in `asia-southeast1` and supports supervised tuning; the latter is
  limited to `global`, `us` and `eu` and does not support tuning. The strict
  Singapore baseline therefore uses `gemini-3.5-flash` as its only regional
  generation candidate. Flash-Lite requires a separate Data/Privacy residency
  decision before it can enter a cost bake-off. VFBIZ-0201 remains
  no-dispatch until its ingestion, retrieval-suite, quota, retention, pricing
  and cost gates are satisfied. The runtime never silently changes model,
  endpoint or region.
- Fine-tuning starts with one SFT candidate only after baseline evidence. Golden
  and voice held-out cases are permanently excluded from tuning.

## Delivery sequence

```text
0192 isolated technical evidence review
-> 0199 cloud ingestion + 0200 ViVi voice candidate
-> 0136 source authority + 0193 Dataset Release
-> 0196 Golden 1,000 + 0139 binding
-> 0201 RAG/model bake-off + 0194 factual assistant
-> 0202 conditional tuning + full reevaluation
-> 0197 supply-chain gate
-> 0195 staging activation
```

At most three disjoint writer lanes may run. Contracts, dataset registry,
migrations, lockfiles and Terraform state each require an exclusive lease.

## Cost and safety envelope

- Monthly development alert: 4,000,000 VND at 50/75/90/100 percent.
- Application admission cap: equivalent of USD 5 per day.
- Live smoke/candidate/full evaluation caps: USD 2/5/20 per run.
- One tuning job at a time, USD 20 maximum and two attempts per root cause.
- Cloud Run uses min instances 0, max instances 2, concurrency 1 and CPU only.
- Budget alerts are not spend enforcement; page/token/job ledgers fail closed
  before provider calls.

## Validation and recovery

- Unit, contract and record/replay tests run without provider spend.
- Live smoke uses synthetic PDFs first and records exact provider/resource
  revisions, usage and evidence digests.
- GCS, Pub/Sub and Document AI failure paths are idempotent and resumable.
- Terraform import/plan must show no replacement of existing resources.
- Every candidate keeps rollback, kill switch and active-pointer isolation.
- Missing rights, approval, Golden lock, cost authority or reviewer independence
  stops only the affected lane.

## Current checkpoint

The approved program has entered delivery. VFBIZ-0199 has reconciled the
observed development GCP foundation into OpenTofu remote state. Destructive R14
was superseded by zero-destroy R16; R16 applied 15 foundation creates and the
post-apply plan is clean. The hardened R20 image is available only at an exact
private Artifact Registry digest. Deployment remains disabled. Migration
`20260802_0024` now supplies disjoint NOLOGIN database capability roles and
passes all 225 PostgreSQL integration tests on a clean disposable database. A
dry-run-first operator command can later bind separate login roles to numeric
Secret Manager versions without putting credentials in Terraform state. No
Cloud SQL login or secret value has been created; independent DB-role review
and the remaining risk/upload evidence are still required.
VFBIZ-0200 may continue as a review-only control-plane foundation. No real
VinFast corpus, managed Dataset, Vertex evaluation or tuning submission is
authorized by this checkpoint.

The assistant routing fallback was also hardened locally: a single keyword
match emits no more than `0.6` confidence, allowing a healthy release-bound
semantic classifier to validate the intent and making classifier outage
fallback explicit. Routing-slice evidence and classifier activation remain
blocked; this change does not alter public Chat state.

Revision 7 adds the default-off private database activation path. The normal
plan digest `2aa3f7d03aeb3ffee030703fe91d54ebd1f0eef98967f2a8fdd88db3152f777b`
is an exact no-change plan. The enabled foundation plan digest
`2588dd29c52bc5b8eb09fc694be0792fecf1d57e43a313e9d8bbd1105a9cca86`
contains 13 creates, 40 no-ops and no update/delete/replacement. It would create
only private networking, PostgreSQL 17, required APIs and three empty protected
secret containers; Cloud Run, push, schedule, SQL users and secret versions
remain absent. Independent risk review found no P0/P1 and one P2 about choosing
automatic versus Singapore-scoped secret replication before any credential
version is published. No apply occurred because the billable shared-core,
Zonal, no-PITR development recovery tradeoff still requires an explicit Cloud
Operator decision. The next code action is a separately gated private bootstrap
job that runs migrations and the reviewed role provisioner without placing
credentials in OpenTofu state.

Revision 8 implements that bootstrap path without activating it. Migration
`20260802_0025` makes bootstrap a database-resident one-shot epoch with a claim,
external authority digest, fencing token and terminal evidence. Role-password
rotation and completion now commit atomically; a thrown commit is reconciled on
a new connection before any external secret cleanup, and an unknown outcome is
left indeterminate rather than guessed. Downgrade refuses to erase any reserved
or terminal bootstrap evidence. The complete fresh PostgreSQL profile passes
231 cases. Operator code is isolated from the OCR worker in a dedicated local
R3 bootstrap image with zero Critical/High findings. It remains unpublished,
unaccepted and unreferenced by Cloud Run. R19 foundation-only plans remain
independently reviewed and create-only, but no apply occurred. The next exact
action is later independent acceptance of the final transaction/downgrade
remediation, followed by an explicit Cloud Operator decision on the billable
foundation plan; bootstrap publication and activation are separate later
packets.

Revision 2 records that VFBIZ-0192 is independently technical-code-complete for
`public-diagnostic`, while `vinfast-acceptance` stays fail-closed on an external
human-witness registrar. The GCP worker service and Pub/Sub dispatch now have
separate IaC switches, the database secret is numeric-version pinned, required
APIs are represented in IaC and the observed Document AI processor revision is
pinned. These changes are validated only; they have not enabled dispatch or
uploaded source content.

Revision 3 records the VFBIZ-0196 candidate packet
`7189b908c558ef60c8b7c8a418a0d97803d7c60ff52facb228ade2e8d4c2e020`:
exactly 1,000 schema-valid, fact-free and release-ineligible cases across 100
locked families. Independent technical review closed the scoped P0/P1 findings.
The historical governed training-only contamination scan found no exact or
lexical token-Jaccard overlap across 1,320 Golden and 8,080 training surfaces.
It was incomplete because governed knowledge and red-team registries did not
yet exist. Red-team coverage now exists at the later checkpoint below;
governed knowledge remains absent. Human adjudication remains 0/1,000; this
checkpoint creates no Golden Release, tuning eligibility or provider dispatch
authority.

The source set for that scan is now resolved from pinned Data Governance
inventory `global-contamination-source-inventory-v1`, rather than supplied by
the scan caller. Independent review then found a remaining digest-only store
bypass. The remediated report
`7f682ad7e1ca1386ff78dff9a0b5d812f5cb28d805cbb9c77ce528d810ac00af`
locks threshold 0.85, rejects zero-surface product evidence and can be stored
only after a complete rebuild from the pinned inventory. It preserves the
correct historical `incomplete` status. Red-team has since been materialized;
knowledge is still absent and later independent acceptance is still required.

VFBIZ-0200 has additionally materialized a 60-case fact-free ViVi voice grader
calibration packet at digest
`4c39920634b2a2d3ca3c379dd7ed3e0d539a06d0ed0d18e9d72ced083626e7f9`.
It is human-blocked, evaluation-only and isolated from Golden/training/release.
Its lexical Golden-isolation diagnostic found no match, but independent domain
review and named Product/Design/Brand/Legal/Data/Release decisions remain open.

VFBIZ-0211 now binds the real Governance release resolver to the sealed
Evaluation semantic authority. A digest-only trusted-evidence row is
insufficient: exact run, bundle, candidate, state and authority fields must
match. Automated evidence remains `needs-human-decision` with no embedded human
approval; the separate Governance approval set remains mandatory. Independent
review closed the initial unsatisfiable-gate P1 after this separation-of-duties
correction, and a real PostgreSQL seal/read test exercises the new facade.

VFBIZ-0196 now also has restricted synthetic red-team packet
`4822afbe2e509e7081f0fd0405ef369a8240f3c4e52d37728a32f8957c576497`:
200 fact-free cases, 40 locked families and eight balanced attack classes. The
inventory-bound contamination report
`87a478cc26591685460acb62800a68a4d80ece79f1e188fea6c8a95ec57d8e3a`
finds no Golden overlap across training and red-team surfaces and remains
`incomplete` only for governed knowledge. Independent red-team review remains
pending because the reviewer provider hit its usage limit; no acceptance is
inferred.

VFBIZ-0199 now materializes restricted synthetic knowledge qualification
packet `50026ed91aa6dfce5b1fa8bebe8aef80e351da3ea151e0892295c8fc6aa595d1`.
Its 12 fact-free page surfaces carry source/page digests and citation lineage,
but explicitly record no cloud OCR and no raw PDF. Inventory-bound
contamination report
`25c05bbc13d27821edbd6a1cf8684d0823bee8a87603d8d9edd0830355873622`
now observes knowledge, red-team and training and returns technical `passed`
with zero exact/lexical match. It is not semantic-equivalence, data-rights,
human-adjudication or release evidence. Independent dataset-quality review is
still pending for the final architecture-corrected digest. The reviewer found
and then closed an external-symlink P1 and caller-authority P2 on the first
remediation; the full suite subsequently forced filesystem authority loading
out of the application layer. The bounded two-cycle review budget is exhausted,
so that final delta is not self-accepted. The delegated implementation provider
also failed authentication before work began and that failure is not
represented as acceptance.

Revision 4 adds the exact synthetic Document AI PDF pilot packet at manifest
digest `2fedefbaff8508672b880f893152661b0367a33166ac7bcde33f063fbacfbd1f`.
Independent dataset review closed its path and font-rights technical findings;
all upload, human, training and release flags remain false. Saved OpenTofu plan
R14 is bound to SHA-256
`3c83e52a21814bba3d868d6f8ae7b537126b4a0a0841f401143345889509226b`
and remains unapplied under `VFBIZ-0199-R14-OPERATOR-PACKET-001`. Worker image
R20 is multi-stage, hardened, non-root and content-free. Its SBOM scan reports
zero Critical/High and two Medium findings in unused Python mail client modules
without a known fix. Health passes and the complete suite passes in an isolated
Python 3.14.6 environment. The zero-destroy foundation plan then applied 15
creates and produced a clean post-apply plan. R20 is published at an immutable
private Artifact Registry digest but is not deployed; Artifact Registry reports
unknown SLSA level. Independent supply-chain review found no new P0/P1 for
private image publication and retained the Document AI project-scope,
data-activation and final-image provenance gates for deployment. The
deterministic default AI gate passes 879 tests with 104 explicit conditional
skips.

## Checkpoint — 2026-08-03

The implementation lanes now include an explicit evaluation qualification
producer, a post-reconciliation Document AI candidate materializer and an
optional materialization boundary on `GcpIntakeRuntime`. Candidate output is
content-addressed, generation/fence-bound, review-gated and never changes an
active retriever. API safety follow-up now persists and reconciles subject
budgets exactly once, requires message idempotency keys, rejects malformed or
gapped replay cache events, maps typed domain errors and derives turn leases
from provider timeout. Runtime release composition now requires an independent
`data-owner` authority in addition to release and security roles.

Observed verification on this checkpoint: `verify:ai` 986 passed / 112 skipped,
fresh AI PostgreSQL integration on a disposable PostgreSQL 17 + pgvector
database passed through `20260802_0025`, API 74 suites / 481 tests plus 76 E2E
tests and build passed, both portal verification paths passed, contracts and
governance passed, and OpenTofu validate passed. Read-only GCP discovery found
only the four private development buckets; no Cloud Run workload, Vertex custom
job, endpoint or custom model exists in the checked regions. The current
default Terraform plan is `0 add, 1 change, 2 destroy` because two stale
disabled-worker IAM bindings still require an operator-reviewed reconciliation.
No apply, upload, OCR, Vertex call or secret-version creation occurred. The
separate staging project is not accessible to the active identity. Public Chat,
Golden adjudication, source/legal/data/brand approval and tuning submission
remain correctly blocked.
