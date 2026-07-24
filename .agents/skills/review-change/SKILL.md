---
name: review-change
description: Review and verify a VFBiz change against acceptance using observed evidence; remain read-only, fingerprint findings and stop within the review budget.
---

# Review a change

1. Read the work item, diff and observed checks; load only affected policy.
2. Verify acceptance and required negative paths with the smallest sufficient checks.
3. Review correctness, regressions, boundaries and missing verification.
4. Return severity, fingerprint, path/evidence, impact and disposition.
5. Merge duplicates and omit preferences unrelated to acceptance or policy.
6. Re-open no finding without new evidence.
7. Stop after the second review/fix cycle and escalate unresolved disagreement.
