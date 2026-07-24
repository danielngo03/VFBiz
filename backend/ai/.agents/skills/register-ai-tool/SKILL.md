---
name: register-ai-tool
description: Add or change a governed VFBiz AI tool using a typed schema, least-privilege scope, deterministic API implementation, authorization, quota and audit controls. Use whenever a model may propose a new tool call or a tool contract changes.
---

# Register an AI tool

1. Resolve the active Git work item. Confirm its approved tool scope, assistant profile, allowed paths, accountable API owner and required human authorities. If scope or authority is absent, stop with a decision request; never infer current release scope from this skill.
2. Classify the tool as read-only or side-effecting. Treat a tool outside the active work item as a scope change.
3. Define strict input/output JSON Schema, scope, timeout, quota, data classification, error mapping and freshness semantics. Reject unknown fields.
4. Keep execution in API Platform. AI may propose a call; API authenticates the caller, authorizes subject/object access, validates input and executes deterministically.
5. Add audit with correlation ID, tool/version, subject reference, outcome and redacted error. Never log secrets, raw PII or full private payloads.
6. For a side effect, require explicit user confirmation, idempotency, a compensating action or rollback, kill switch and human-approved risk review.
7. Test malformed schema, missing scope, cross-subject access, timeout, quota, provider replay and disabled-mode behavior.
8. Pin the tool registry revision in the AI Release Manifest and return observed evidence. Do not approve or publish the release yourself.
