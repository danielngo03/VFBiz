# Candidate quality gates

Every candidate shard must pass:

1. JSONL parse and Dataset Example schema.
2. Unique example IDs and allowed-use/purpose separation.
3. Approved source grounding or explicit synthetic fact namespace.
4. Secret/PII scan and mandatory human-review flag for high-risk labels.
5. Exact hash and semantic near-duplicate scan within and across shards.
6. Held-out/training/knowledge contamination check.
7. Coverage report by locale, profile, risk and expected outcome.
8. Pinned judge rubric evidence and independent stratified human review.

Pricing, safety, legal, PII and tool-authorization cases receive 100% human
review. LLM-as-a-Judge can rank or flag but cannot accept a gate. Candidate
failure is quarantined with reason; it is never silently repaired into release.
