---
id: agent-runtime-operations
title: Agent runtime local operations and recovery
status: active
owner_role: engineering-lead
scope: agent-runtime
when_to_read:
  - agent-runtime
  - agent-recovery
  - agent-approval
tags:
  - agents
  - operations
  - recovery
revision: 4
review_date: 2026-08-30
supersedes: []
---

# Agent runtime local operations and recovery

## Interactive Codex versus runtime

For normal human-led work, open Codex at the repository root or use `codex -C`
with the owning workspace. Codex discovers `.codex/config.toml`, root and
nearest workspace instructions, registered agents and repository skills
without starting a runtime worker. Repository hooks remain an optional
provider enforcement layer and require the human to trust them in the Codex
client.

Start this runtime only when the work needs a durable queue, restart recovery,
typed multi-agent orchestration, asynchronous approval or runtime evidence.

## Overnight handoff

Before the operator leaves, the current atomic action must finish and the
canonical work-item checkpoint must record revisions, changed paths, observed
checks, blockers and one exact next action. Provider chat history is not a
handoff artifact.

On the next Codex Desktop session, run:

```sh
npm run agent-runtime:doctor
npm run agent-runtime:brief -- --work VFBIZ-NNNN --target <workspace>
```

The brief combines the current Git/work-item context with SQLite operational
state. It contains bounded work-item excerpts, source hashes, run/checkpoint
metadata, pending approval identities, artifact references, usage and event
digests. It intentionally omits objectives, approval reasons, raw payloads and
decrypted checkpoint state. A stale context, worker heartbeat or approval is a
decision packet, never permission to auto-resume.

## Startup

Run `agent-runtime doctor` before a worker. Live OpenAI and Codex flags are off
by default. Configure a fresh base64 32-byte state key outside the repository
before a run can save an agent checkpoint. The state directory and database are
owner-only. When OpenAI is enabled, doctor also requires an API key and explicit
non-negative input/output USD-per-million rates so cost checks cannot silently
be skipped.

For controlled work, enqueue requires `--claim` and `--fencing-token`. The
runtime asks the existing agent-control CLI to validate claim state, fencing,
context identity and every allowed path before dispatch and again on resume.

Codex is exposed to Agents SDK only when both live feature flags are
intentionally enabled. Every call copies a registered source under
`tests/fixtures` into a fresh temporary Git repository and linked worktree. The
adapter verifies a runtime attestation, branch, Git common directory and full
symlink-free tree before and after MCP execution, then disposes the fixture.

## Recovery

The worker commits intent, checkpoint and transition records independently of
the provider. On restart it reconciles stale heartbeats and resumes from the
latest authenticated checkpoint. A checkpoint saved just before an approval
record is recreated from the still-interrupted SDK state with the same call ID
and payload digest. Idempotent enqueue/event/approval keys prevent duplicate
records. Codex writes use a separate intent/completion ledger; an uncertain
operation is stopped for reconciliation rather than replayed.

Provider completion is not acceptance: before any returned artifact or finding
is accepted, the runtime re-resolves context and validates the claim/fencing
token a second time. Usage is still recorded if authority expired during the
provider call. A cancellation requested just before a worker crash is finalized
as `cancelled` by stale reconciliation and is never re-queued.

## Approval

List and inspect the exact request, then decide as
`human:<required-authority>`. The CLI stores the immutable decision; it does not
provide production-grade identity. Rejection fails the affected run safely.
Agents and role names are rejected as decision identities.

## Disable and rollback

Stop the local worker and unset feature flags. Existing Git work items, claims
and commands continue unchanged. The SQLite ledger can be archived after its
retention decision; no product database or work-item migration is required.
