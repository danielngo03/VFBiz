---
name: operate-gcp-ai
description: Operate the VFBiz GCP AI development foundation with imported IaC, workload identity, bounded smoke tests, cost controls and reversible recovery.
---

# Operate GCP AI

1. Resolve the active controlled work item and exact project/region from the
   private operator packet; never infer billing or production scope.
2. Read `infra/gcp/README.md` and the nearest AI ingestion/evaluation policy.
3. Use `tofu plan` and import existing resources before any apply. Stop on
   replacement, public IAM, missing state lock, missing budget or drift.
4. Use workload identity/application default credentials only. Never create or
   commit service-account keys, `.env` files or raw provider output.
5. Run synthetic fixture smoke first. Keep raw VinFast content blocked until the
   source and purpose gates contain human evidence.
6. Enforce page, byte, token, request, retry, concurrency and daily cost caps
   before provider calls. Record immutable job/operation/object digests.
7. Verify Pub/Sub duplicates/out-of-order delivery, Document AI resume/DLQ,
   GCS generation/checksum and rollback/tombstone behavior.
8. Never activate a retriever, public API, model or release from this skill.
