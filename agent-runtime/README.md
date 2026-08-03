# VFBiz Enterprise Agent Runtime

`@vfbiz/agent-runtime` is an additive, local control plane for enterprise agent
work. It deterministically resolves VFBiz governance, persists restart-safe
operational state in SQLite, uses OpenAI Agents SDK behind a bounded port and
exposes Codex as a fixture-only coding specialist.

It does not replace the Git work-item lifecycle, serve a public endpoint, call
product databases or grant agents release authority. Turning it off leaves the
existing VFBiz workflow unchanged.

## Daily interactive Codex

You do not start this runtime for normal Codex work. Start Codex at the
repository root or directly in the owning workspace:

```sh
cd /path/to/VFBiz
codex

codex -C backend/api
codex -C backend/ai
codex -C mobile/customer
codex -C agent-runtime
```

Codex loads the repository `.codex/config.toml`, root instructions, the nearest
workspace `AGENTS.md` and available VFBiz skills automatically. Review and trust
repository hooks once in the Codex client before relying on hook enforcement.
No runtime worker, state key or OpenAI API key is required for this interactive
mode.

Use the runtime only for queued work that must survive restart, coordinate
typed specialists, pause for approval or retain an operational ledger.

## Overnight-to-Desktop handoff

The runtime and Codex Desktop do not share provider conversation memory. They
share canonical Git work state plus the single-host SQLite ledger. Before
leaving a worker unattended, update the work-item checkpoint with observed
checks, blockers and one exact next action. The next Codex Desktop session
reconstructs a bounded packet with:

```sh
npm run agent-runtime:brief -- --work VFBIZ-NNNN --target <workspace>
```

The brief resolves current instructions and source hashes, reports stale
context, run state, pending approval, artifact references, usage and recent
event digests. It never decrypts the Agents SDK checkpoint or returns raw event
payloads. An expired/missing context cache causes a full fresh resolve and
marks old runtime authority stale.

An overnight worker still requires an active governed work item, a valid claim
and fencing token, explicit budgets, a checkpoint key and intentionally enabled
live-provider flags. V1 remains fixture-only for coding execution: it cannot
write VFBiz product workspaces while you sleep.

## Local commands

```sh
npm run agent-runtime -- enqueue --work VFBIZ-0204 --claim <claim-id> --fencing-token <token>
npm run agent-runtime -- worker --once
npm run agent-runtime -- status --run <run-id>
npm run agent-runtime:brief -- --work VFBIZ-0204 --target agent-runtime
npm run agent-runtime -- approvals list
npm run agent-runtime:doctor
npm run agent-runtime:eval
```

OpenAI execution requires both `VFBIZ_AGENT_RUNTIME_OPENAI_ENABLED=true` and an
`OPENAI_API_KEY`. Encrypted checkpoints require a base64-encoded 32-byte key in
`VFBIZ_AGENT_RUNTIME_STATE_KEY`. Live cost enforcement also requires
`VFBIZ_AGENT_RUNTIME_INPUT_USD_PER_1M` and
`VFBIZ_AGENT_RUNTIME_OUTPUT_USD_PER_1M`. None of these values belongs in Git.

Controlled work cannot be enqueued without the current canonical claim and
fencing token. The runtime validates both, the exact allowed paths and the
context revision through the existing agent-control CLI before provider work.

See [architecture](docs/architecture.md), [operations](docs/operations.md) and
[evaluation](docs/evaluation.md).
