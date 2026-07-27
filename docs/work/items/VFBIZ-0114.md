---
id: VFBIZ-0114
title: Persist and compose Assistant Release authority
status: done
mode: controlled
priority: P0
owner_team: ai-assurance
accountable_role: release-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/migrations/versions/20260727_0013_trusted_release_registry.py
  - backend/ai/app/modules/governance/application
  - backend/ai/app/modules/governance/domain
  - backend/ai/app/modules/governance/infrastructure
  - backend/ai/tests/evaluation/test_assistant_release_manifest.py
  - backend/ai/tests/integration/governance
depends_on:
  - VFBIZ-0104
  - VFBIZ-0116
  - VFBIZ-0117
controlled_signals:
  - ai-release
  - ai-safety
  - ai-retrieval
exclusive_resources:
  - ai-assistant-release-manifest
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 8
review_date: "2026-08-26"
updated_at: "2026-07-27T04:32:43.931Z"
---

# Outcome

Một activation ID được resolve từ PostgreSQL thành đúng immutable Assistant
Release Candidate, approval/gate evidence, rollback target và live-control
evidence; mọi stale, revoked, cross-profile hoặc digest-mismatch activation đều
fail closed trước khi runtime provider được gọi.

## Constraints

- PostgreSQL là authority; environment variable chỉ chọn activation ID dự kiến.
- Activation dùng OCC và append-only audit; candidate artifact identity là
  immutable.
- Rollback target phải là candidate từng được activation hợp lệ trong cùng
  profile/environment, không tự tham chiếu hoặc tạo cycle.
- Artifact reader chỉ resolve opaque internal reference, không fetch URL tùy ý.
- Repository lane không compose Model Mesh, migration hoặc retrieval business
  logic; các phần đó thuộc `VFBIZ-0116`, `VFBIZ-0117` và `VFBIZ-0115`.

## Done when

- Repository resolve snapshot nhất quán trong một transaction và kiểm tra
  effective window/revocation.
- Rollback lookup chứng minh target từng active/superseded hợp lệ và chặn cycle.
- Canonical schema, domain object và persistence round-trip không drift.
- Store, trusted opaque digest reader và authentic evidence verifier có typed
  infrastructure errors, deadline/cancellation và bounded concurrency.
- Integration tests thật với PostgreSQL bao phủ activate, revoke, concurrent
  update, stale pointer, rollback và restart recovery; không skip.
- Coordination Request
  `coord-222d8925-38cb-49bb-841f-7ec951068b75` được phản hồi/đóng bằng evidence.

## Checkpoint

- Review cycle 1 đã phát hiện và khắc phục hai nhánh compatibility fail-open:
  runtime manifest hiện bắt buộc activation core/envelope, promotion evidence
  và typed rollback target; legacy candidate-only rollback đã bị loại bỏ.
- Prior activation hiện đối chiếu cả embedded static-safe document với hàng
  PostgreSQL tương ứng trước khi dựng domain object.
- `PostgresTrustedReleaseRegistry` và migration `20260727_0013` cung cấp
  artifact/evidence authority fail-closed; revoked record không còn resolve.
- Review snapshot digest cho đúng lane tại checkpoint này:
  `0a1458dae4040b534bd80ccedb99e5317e28cf206f1e495845aea3f1718facbd`.
- Exact next action: independent reviewer-verifier và risk-reviewer chạy cycle
  2 trên snapshot digest trên.

## Evidence

- [x] `VFBIZ_RUN_DB_INTEGRATION=1 npm run verify:ai` — ruff clean, pyright 0
  errors, 318/318 tests passed (0 skipped) against a migrated PostgreSQL
  database, alembic upgrade head generated cleanly on 2026-07-26.
- [x] `npm run governance:check` — passed on 2026-07-26.
- [x] `VFBIZ_RUN_DB_INTEGRATION=1 uv run pytest` — 429 passed, 0 skipped on
      2026-07-27 after migration `20260727_0013`.
- [x] Focused release authority + trusted registry integration — 23 passed,
      including fail-closed revocation.
- [x] Independent cycle-2 reviewer-verifier — approved snapshot
      `0a1458dae4040b534bd80ccedb99e5317e28cf206f1e495845aea3f1718facbd`.
- [x] Independent cycle-2 risk review — approved with in-flight revocation
      fencing/OCC/history residual risk assigned to VFBIZ-0126; VFBIZ-0115 is
      now hard-blocked on VFBIZ-0126.

### blocked — 2026-07-26T05:26:37.689Z

Ownership audit found one writer spanning Data Governance contracts, AI Assurance persistence and Platform Foundation migrations; split lanes before claim.

### active — 2026-07-26T10:32:31.647Z

Dependencies complete; implementing PostgreSQL release resolver before runtime provider binding

### active — 2026-07-26T22:00:00.000Z

Rollback-verification hardening (`_verify_prior_activation_readiness`) closed
the fail-open gap where a rollback target could resolve without being
re-checked for effective window, revocation, live-control readiness or a
pinned static-safe fallback. All "Done when" criteria are met except
Coordination Request `coord-222d8925-38cb-49bb-841f-7ec951068b75`, which this
session could not locate in local coordination state to respond to or close;
Release Owner should confirm its current status before moving this item to
review.

### review — 2026-07-27T04:05:17.184Z

The previously missing coordination record was located in the shared Git
control state, responded to by `ai-platform-foundation` with VFBIZ-0116
evidence, and closed by `ai-assurance`. Release resolver implementation is
now awaiting independent verifier/risk-review evidence; no release has been
promoted by this transition.
