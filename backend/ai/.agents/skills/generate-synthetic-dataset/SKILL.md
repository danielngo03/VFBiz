---
name: generate-synthetic-dataset
description: Generate one bounded VFBiz synthetic dataset candidate shard from an approved generation job, schema, seed and synthetic fact namespace; use for evaluation, red-team, state, tool or conversation-quality cases that require deterministic validation, deduplication and an independent review handoff. Never use with production PII or to approve a release.
---

# Generate a synthetic dataset shard

1. Resolve the controlled work item and read `references/generation-contract.md`.
2. Validate the approved Generation Job, budget, input source rights and a unique
   shard lease. Stop if output prefix overlaps another writer.
3. Use only approved seeds/source references or clearly synthetic fact namespace.
   Never read production PII, customer chat or held-out evaluation data.
4. Generate records directly against `contracts/ai/dataset-example.schema.json`.
   Stop at record/token/cost budget; do not retry the same failure over twice.
5. Run:
   - `scripts/validate_candidate.py --input <shard.jsonl>`
   - `scripts/detect_near_duplicates.py <shard.jsonl> [other-shards...]`
   - `scripts/build_manifest.py ...`
6. Read `references/quality-gates.md`; quarantine failed records with reason.
7. Handoff immutable shard/manifest hashes to `dataset-quality-reviewer`.
   Do not edit Source Register, approval or released dataset state.

## Stop conditions

- Missing approved generation job, seed/source rights, budget or shard lease.
- Production/customer PII, hidden evaluation split or factual VinFast value
  without approved source/synthetic namespace.
- Schema, secret/PII, contamination or duplication gate fails.
- Requested output is Git-tracked large data or a registry/release path.

## Output

Return record/rejection counts, shard/manifest hash, observed command evidence,
coverage gaps, residual risks and exact next action for independent review.
