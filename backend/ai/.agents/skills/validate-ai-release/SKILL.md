---
name: validate-ai-release
description: Produce immutable, reproducible evaluation evidence for a VFBiz AI release candidate across profile isolation, retrieval, citations, refusal, tools, datasets, cost and rollback before independent human decisions.
---

# Validate an AI release

1. Read `backend/ai/docs/evaluation-and-release.md`. Pin candidate, baseline,
   assistant profile, model/provider, prompt, policy, retriever, embedding,
   datasets, tool registry and held-out suite revisions.
2. Confirm candidate author and independent evaluator identities/roles. Check
   source hashes/near-duplicates so evaluation/red-team cases have not leaked
   into knowledge, training or prompt examples.
3. Run each profile suite separately with pinned environment, seed/sampling
   policy and metric definitions. Repeat the acceptance-critical run as required
   to expose non-deterministic failure.
4. Enforce hard gates individually: zero ACL/PII leakage; factual response has
   valid citation or refusal/handoff; unauthorized/malformed/disabled tools are
   rejected; provenance, rollback and kill switch evidence exists.
5. Compare groundedness, usefulness, refusal quality, latency and cost against
   the versioned acceptance target and current baseline. Do not invent a target
   when active acceptance does not define one.
6. Test injection, poisoned source, cross-subject access, provider/quota failure,
   cache isolation and rollback. Record redacted failures and evidence hashes.
7. Return an immutable evaluation report with per-gate result, residual risk and
   recommendation to Data/Security/Privacy/Legal and Release authorities.

Do not approve, publish, accept residual risk or claim that an AI system can
never be wrong. Missing independence, provenance, ACL isolation, reproducibility
or rollback is a failed-safe exit.
