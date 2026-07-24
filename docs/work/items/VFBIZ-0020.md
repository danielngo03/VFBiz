---
id: VFBIZ-0020
title: LangGraph dependency và private protocol foundation
status: proposed
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
  - backend/ai/app/api
  - backend/ai/app/platform
  - backend/ai/tests/contract
depends_on:
  - VFBIZ-0019
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
revision: 1
review_date: "2026-08-23"
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
- Contract tests dùng fixture chung từ `contracts/ai`.
- Dependency audit, Ruff, Pyright, Pytest và Alembic dry-run đạt.

## Checkpoint

- Exact next action: chỉ start sau VFBIZ-0019; cập nhật dependency và private
  verifier trong một atomic checkpoint.

## Evidence

- [ ] `npm run verify:ai` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
