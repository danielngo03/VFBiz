---
id: VFBIZ-0193
title: Operationalize Dataset release authority
status: active
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai/app/modules/datasets
  - backend/ai/tests/unit/datasets
  - backend/ai/tests/integration/datasets
  - backend/ai/tests/security/datasets
  - backend/ai/migrations
  - backend/ai/dataset-specs
  - docs/work/items/VFBIZ-0193.md
  - WORK.md
depends_on:
  - VFBIZ-0190
  - VFBIZ-0183
  - VFBIZ-0184
  - VFBIZ-0185
  - VFBIZ-0186
  - VFBIZ-0187
controlled_signals:
  - ai-dataset
  - dataset-release
  - human-adjudication
  - migration
exclusive_resources:
  - ai-dataset-registry
  - database-migration
required_checks:
  - npm run verify:ai
  - npm run verify:ai:integration
  - npm run governance:check
revision: 3
review_date: "2026-08-29"
updated_at: "2026-07-29T18:45:46Z"
---

# Outcome

Bind Dataset release to immutable quality, scan and independent approval
evidence and execute the lifecycle through durable idempotent workers.

## Constraints

- Agents prepare evidence but cannot create human approval.
- Golden, evaluation and red-team products remain isolated from training and knowledge.
- Generated evidence and downloaded payload do not enter Git.

## Done when

- PostgreSQL rejects release without current quality and reviewer evidence.
- Worker delivery, lease expiry, retry, cancellation and DLQ tests pass.
- Rollback, tombstone, retention and deletion lineage are durable.
- DLP and structured-file scanning cover the approved enterprise policy.

## Checkpoint

- VFBIZ-0183–0187 provide manifest semantics, provenance resolution,
  PostgreSQL promotion fencing and bounded SERIALIZABLE registry transitions.
- This lane will not fetch or ingest first-party VinFast content. Missing
  Content/Legal/Data approval remains a failed-safe human gate.
- Implementation is stopped before source fetch/release because required human
  authority inputs below do not exist. This is not a code or agent permission
  blocker.
- Exact next action: the named operators complete the packet below; then resume
  immutable quality/reviewer evidence and worker/DLQ implementation.

## Human operator packet

1. **Content Owner** supplies one first-party VinFast source with exact HTTPS
   locator, immutable revision, custodian, content scope and freshness owner.
2. **Legal Owner** records commercial/derivative/fetch rights, terms digest,
   prohibited uses, retention and deletion method. The decision must have an
   immutable decision ID, evidence URI, SHA-256, actor and timestamp.
3. **Privacy/Data Owner** publishes the enterprise DLP policy ID/revision,
   required PII/secret categories, thresholds, allowed classification/ACL,
   approved purpose and expiry. Reviewer and approver must be distinct humans.
4. Save the resulting Source Register candidate outside Git, then run:

   ```text
   python backend/ai/.agents/skills/onboard-dataset/scripts/validate_source_entry.py \
     --register <approved-source-register.json> --source-id <source-id> --gate fetch
   ```

5. Only after step 4 passes, the egress-restricted operator may run
   `fetch_to_quarantine.py` for that exact locator. Record the content SHA-256,
   tree hash, bytes, media type, quarantine URI and scan report; do not place
   payloads or reports containing PII in Git.
6. After malware, structural, secret, PII and rights scans pass, run the same
   validator with `--gate purpose --purpose <approved-purpose>
   --fetch-manifest <scan-passed.json>`.
7. Provide immutable quality-run IDs, independent reviewer decision IDs,
   worker lease-expiry/retry/cancel/DLQ drill evidence, rollback/tombstone
   evidence and retention/deletion completion evidence.

Resume criteria: all decision IDs resolve in the human approval registry,
digests match the exact source/fetch/artifact revisions, no reviewer is the
author/generator, and VFBIZ-0183/VFBIZ-0185 are no longer active.

### active — 2026-07-29T18:45:46Z

Controlled implementation activated from the reviewed v4/provenance
foundations. No dataset or human approval was synthesized.

### human-blocked — 2026-07-29T18:45:46Z

Stopped before network access under `onboard-dataset`: first-party source
rights, enterprise DLP policy and named Content/Legal/Privacy/Data decisions
are missing.

## Evidence

- [ ] `npm run verify:ai` — add observed evidence.
- [ ] `npm run verify:ai:integration` — add observed evidence.
- [ ] `npm run governance:check` — add observed evidence.
