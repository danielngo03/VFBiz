---
id: VFBIZ-0206
title: Align Codex config validation and mobile governance scenario
status: review
mode: controlled
priority: P1
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
  - mobile
allowed_paths:
  - tests/governance/scenarios.json
  - tools/check-agent-governance.mjs
  - docs/work/items/VFBIZ-0206.md
  - WORK.md
  - docs/INDEX.md
  - docs/INDEX.json
depends_on: []
controlled_signals:
  - provider-parity
  - agent-control
exclusive_resources: []
required_checks:
  - governance:check
  - adapters:check
  - docs:check
revision: 4
review_date: "2026-07-30"
updated_at: "2026-07-30T15:08:55.914Z"
---

# Outcome

Make agent-governance validate the installed Codex CLI configuration and the
current mobile workspace topology, so valid provider setup passes and stale
instruction paths fail deterministically.

## Constraints

- Root governance fixtures and checker logic only; do not recreate
  `mobile/AGENTS.md`, `mobile/CLAUDE.md` or `mobile/README.md`.
- Parse `.codex/config.toml` as TOML and validate supported installed keys;
  do not preserve obsolete raw-text expectations.
- Preserve the unrelated source-intake governance additions already present in
  the dirty checker file and edit only the provider-instruction section.

## Done when

- Codex configuration validation requires `agents.max_threads`,
  `agents.max_depth` and an explicit config file for every registered worker
  role.
- Registered workspaces with a sibling `AGENTS.md` require a thin sibling
  `CLAUDE.md`; deliberate container workspaces without `AGENTS.md` are allowed.
- The mobile fast-mode scenario resolves `mobile/customer/README.md` to the
  registered mobile workspace and owner team.
- Governance, adapter and documentation checks pass.

## Checkpoint

- 2026-07-30: local Codex 0.144.5 config inspection proved that
  `agents.max_threads` and `agents.max_depth` are accepted, while the old
  `max_concurrent_threads_per_session` expectation is stale.
- 2026-07-30: the mobile scenario was updated under a scoped claim. The checker
  integration changed only the earlier provider-instruction section and
  preserved the separate source-intake diff beginning in schema validation.
- Exact next action: obtain independent read-only acceptance review; the
  deterministic gates are green.

## Evidence

- [x] `governance:check` — 2026-07-30: full governance passed, including 75
  provider-neutral context scenarios.
- [x] `adapters:check` — 2026-07-30: generated adapters match the organization.
- [x] `docs:check` — 2026-07-30: generated index is current at 93 documents.
- [x] Codex config — parsed TOML matches installed CLI behavior: three threads,
  depth one and an explicit config file/description for all nine workers.

### ready — 2026-07-30T15:02:07.137Z

Installed Codex config and mobile topology were observed locally; scope is root governance only.

### active — 2026-07-30T15:02:07.437Z

Begin one agent-platform governance lane; no mobile product files may be edited.

### review — 2026-07-30T15:08:55.914Z

Governance correction is green; independent read-only acceptance remains required.
