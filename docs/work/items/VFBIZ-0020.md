---
id: VFBIZ-0020
title: LangGraph dependency và private protocol foundation
status: done
mode: controlled
priority: P0
owner_team: ai-platform-foundation
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/pyproject.toml
  - backend/ai/uv.lock
  - backend/ai/app/bootstrap/application.py
  - backend/ai/app/api
  - backend/ai/app/platform
  - backend/ai/tests/contract
  - backend/ai/tests/unit/platform
depends_on:
  - VFBIZ-0019
  - VFBIZ-0089
controlled_signals:
  - ai-assistant
  - dependency-policy
  - license
  - authorization
  - pii
exclusive_resources:
  - dependency-lockfile
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 7
review_date: "2026-08-23"
updated_at: "2026-07-24T18:59:43.689Z"
---

# Outcome

FastAPI có dependency LangGraph được pin/review và private endpoint/verification
foundation tương thích Conversation Turn Protocol v1, chưa chứa graph nghiệp vụ.

## Constraints

- Dependency/license/supply-chain review và `dependency-lockfile` lease bắt buộc.
- FastAPI chỉ nhận request từ NestJS qua signed assertion allowlist.
- Không mở route AI public và không dùng provider/model name làm domain module.

## Done when

- `pyproject.toml`/`uv.lock` pin LangGraph version đã được review.
- Private schema verifier từ chối employee profile, assertion expired, replay,
  sai audience/version/fencing/budget.
- Checkpointer contract tách AI execution state khỏi durable business
  conversation; checkpoint không được trở thành customer history authority.
- Contract tests dùng fixture chung từ `contracts/ai`.
- Dependency audit, Ruff, Pyright, Pytest và Alembic dry-run đạt.

## Checkpoint

- Exact next action: chỉ start sau VFBIZ-0019; cập nhật dependency và private
  verifier trong một atomic checkpoint.

## Evidence

- [x] `npm run verify:ai` — PASS; Ruff, Pyright, 48 Pytest cases and Alembic
  SQL dry-run succeeded.
- [x] `npm run governance:check` — PASS; documentation/report drift, 86 work
  items and 61 provider-neutral routing scenarios remain valid.

### Additional observed evidence

- `npm run contracts:lint` — PASS without warnings after VFBIZ-0089 froze
  profile/tool, error, cancellation and canonical-hash semantics.
- `uvx pip-audit --path backend/ai/.venv/lib/python3.12/site-packages --strict`
  — no known vulnerabilities.
- Independent review cycles — no P0; all P1 findings were resolved, including
  locale binding, durable cancellation receipt, unknown-key classification,
  JWKS origin/timeout policy, problem parity and data-minimized checkpoints.
- mTLS remains a required deployment/service-mesh evidence gate before staging;
  this foundation does not claim transport deployment is complete.

### ready — 2026-07-24T18:36:14.291Z

VFBIZ-0019 is done; dependency and private assertion scope is ready.

### active — 2026-07-24T18:36:14.570Z

Implementing signed assertion verification, replay boundary and checkpoint contract without graph business logic.

### checkpoint — 2026-07-24T18:45:20.659Z

Foundation checkpoint `0e90140` passed AI and governance gates. Independent
review found contract/security drift requiring one controlled fix cycle across
the shared assertion/OpenAPI contract and FastAPI response/configuration
boundary.

### checkpoint — 2026-07-24T18:59:14.751Z

Runtime hardening commit `649b44f` implements the frozen VFBIZ-0089 contract,
passes all required gates and leaves business graph execution disabled until
VFBIZ-0021.
