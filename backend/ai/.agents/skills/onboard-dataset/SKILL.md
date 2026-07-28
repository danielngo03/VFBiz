---
name: onboard-dataset
description: Register, quarantine and prepare a VFBiz knowledge, evaluation, red-team or external dataset source when provenance, license, permitted purpose, classification, ACL, retention and deletion evidence must be verified before any download or ingestion. Never use it to approve or release a dataset.
---

# Onboard a dataset

1. Resolve work item, Data Owner, permitted purpose and assistant profile.
2. Read `references/source-gate.md` and the exact sections selected from
   `backend/ai/docs/knowledge-data-governance.md`.
3. Create/update a Source Register candidate without downloading content.
4. Before network access run `scripts/validate_source_entry.py --register
   <path> --source-id <id> --gate fetch`. This requires exact revision,
   allowlisted origin, rights evidence and human fetch approval; an upstream
   checksum is optional because the observed hash does not exist yet.
5. Use `scripts/fetch_to_quarantine.py` in the egress-restricted fetch worker.
   It accepts only the approved exact HTTPS locator, rejects redirects and
   streams a bounded JSON/JSONL/CSV/Parquet artifact to content-addressed
   quarantine. Record its Source Fetch Manifest with observed SHA-256/tree
   hash. Scan malware, secrets,
   PII, rights conflicts, poisoning and format before parsing.
6. Before parsing or evaluation run the same validator with `--gate purpose
   --purpose <purpose> --fetch-manifest <scan-passed.json>`. Pin purpose, source revision/hash, classification, ACL, retention,
   deletion/tombstone and generation/ingestion budget.
7. Keep knowledge, held-out evaluation, red-team and training candidate separate.
8. Submit immutable evidence to independent reviewer and human authorities.
   Author/generator does not approve or publish.

## Stop conditions

- Rights, owner, fetch/purpose approval, ACL, retention or deletion evidence missing.
- Customer/production data proposed without explicit privacy/legal authority.
- Evaluation/red-team records overlap knowledge or training candidate.
- Download destination is Git, prompt context, logs or an unapproved store.
- Same failed gate has already been retried twice without new evidence.

## Output

Return Source Register ID/revision, quarantine artifact hash (if authorized),
checks observed, rejected reasons, required human decision and exact next action.
Never return source payload, secret or PII.
