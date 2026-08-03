---
name: build-tuning-candidate
description: Build a governed Vertex tuning candidate from an approved, split-locked dataset without submitting or promoting a job.
---

# Build tuning candidate

1. Resolve a controlled tuning work item with Dataset, Golden, evaluator and
   provider revisions pinned.
2. Keep knowledge, evaluation, red-team and training products separate. Golden
   and held-out cases never become training records.
3. Require source rights, purpose, privacy, DLP, retention and deletion evidence
   before export. Customer chat is excluded unless explicitly approved.
4. Partition by conversation family before synthesis; write immutable train,
   validation and test manifests with contamination fingerprints.
5. Run deterministic schema, PII/secret, prompt-injection, duplicate and
   split-leakage checks before any Vertex call.
6. Export SFT or preference JSONL only. Export must not submit a tuning job.
7. Keep a human-authorized submission packet with model, region, dataset digest,
   budget, attempt limit, rollback and kill-switch references.
8. AI Assurance evaluates the candidate against untouched held-out evidence.
   The builder, evaluator and Release Owner must be different authorities.
9. Never use tuning to store facts, repair ACL/freshness, or bypass a release
   gate; stop on missing authority or budget.
