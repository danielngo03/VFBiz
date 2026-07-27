---
id: VFBIZ-0126
title: Implement concrete AI release kill-switch registry
status: done
mode: controlled
priority: P1
owner_team: ai-assurance
accountable_role: release-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/modules/governance
  - backend/ai/migrations
  - backend/ai/tests/integration/governance
  - backend/ai/tests/security
depends_on:
  - VFBIZ-0114
controlled_signals:
  - ai-release
  - ai-safety
exclusive_resources: []
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 5
review_date: "2026-07-26"
updated_at: "2026-07-27T04:56:59.884Z"
---

# Outcome

`TrustedArtifactRegistry`/`TrustedEvidenceRegistry` (currently Protocols only,
`trusted_release_artifacts.py`) get a real, production-capable implementation,
so a revoked kill-switch actually blocks resolution within a bounded time
instead of only being checked as an evidence digest.

## Constraints

- Six existing work items (VFBIZ-0007, 0026, 0085, 0094, 0100, 0124) already
  reference "kill switch" as a required condition; none of them build the
  concrete registry. This item exists so exactly one work item owns that, not
  to duplicate their scope.
- Ownership assumption to confirm before starting: this sits in
  `app/modules/governance/infrastructure`, so `ai-assurance` is proposed as
  owner, but `ai-platform-foundation` (shared infrastructure) is a reasonable
  alternative — Engineering Lead should confirm before claiming this item.
- Revocation must propagate to `PostgresReleaseAuthorityResolver.resolve`
  within the same freshness window already enforced for pointer staleness
  (see VFBIZ-0114's `_assert_fresh`), not a separate, weaker guarantee.
- No mock/no-op registry may ship as the production default; the existing
  `FailClosedClaimSupportValidator`-style default (fail closed until real)
  is the correct interim state, not a registry that always returns "clear".

## Done when

- A concrete registry (Postgres-backed, consistent with the rest of the
  governance module's persistence) implements both Protocols with typed
  errors, deadline/cancellation and bounded concurrency, matching the
  pattern already used by `PostgresReleaseAuthorityResolver`.
- Integration tests prove a revoked kill-switch blocks a resolution already
  in flight and one issued after revocation, both against real PostgreSQL.
- The six referencing work items' "kill switch" conditions are satisfied by
  this registry rather than left as an unimplemented assumption.

## Checkpoint

- Registry ghi immutable revision receipt trong một context-local resolution
  scope; `PostgresReleaseAuthorityResolver` final-compare trust receipts sau
  pointer/history freshness và trước khi trả resolved release.
- Revoke dùng expected revision, actor, reason và idempotency key trong cùng
  transaction; database trigger chỉ cho `active → revoked`, revision tăng đúng
  một và chặn sửa trust identity.
- Mỗi revoke tự ghi append-only history và transactional outbox; `revoked →
  active` bị database từ chối.
- Migration `20260727_0014` và integration tests bao phủ lookup revocation,
  revoke sau lookup, final resolver fence, irreversible transition và
  history/outbox.
- Review cycle 1 findings đã được khắc phục:
  - receipt collector là mutable scope object dùng chung với child task;
  - final compare là một SQL statement atomic;
  - trust fence là constructor dependency bắt buộc;
  - real resolver + real PostgreSQL registry test revoke trước final return;
  - idempotency replay bind expected revision, actor và reason;
  - registry DELETE và outbox identity/payload mutation bị DB trigger chặn.
- Exact next action: independent cycle-2 review xác minh năm remediation trên.

## Evidence

- [x] `npm run verify:ai` — Ruff/Pyright/Alembic passed; default suite passed,
      with DB integration separately forced below.
- [x] `npm run governance:check` — passed with 126 WorkItemV2 files and 72
      provider-neutral routing scenarios.
- [x] `VFBIZ_RUN_DB_INTEGRATION=1 uv run pytest tests` — 433 collected and
      passed, 0 skipped.
- [x] Focused release authority/trusted registry suite — 27 passed.
- [x] Ruff/Pyright — clean.
- [x] Independent reviewer-verifier cycle 2 — approved relevant snapshot
      `dc0f6f8c90e3a0b881249e88db4f31f19d947dd9299f531cc8ce02b32532f284`.
- [x] Independent risk-reviewer cycle 2 — approved; production composition
      must reuse the same registry instance for digest, evidence and fence.
