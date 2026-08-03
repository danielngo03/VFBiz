---
name: operate-agent-runtime
description: Operate the VFBiz single-host enterprise agent runtime for governed enqueue, recovery, approval and synthetic fixture evaluation without product mutation or release authority.
---

# Operate the VFBiz agent runtime

1. Resolve a canonical active work item and use its exact target path. Do not
   infer a product write, human authority or owner from chat history.
2. Run `npm run agent-runtime:doctor`. Stop if `agent-runtime` is unregistered,
   `multiMachineReady` is true, the state directory is not owner-only or a live
   feature is enabled unexpectedly.
3. Keep OpenAI, Codex and tracing feature flags off for deterministic intake.
   Before a live sandbox run, provide a fresh base64 32-byte checkpoint key
   outside Git, explicit input/output USD-per-million rates and confirm the work
   item permits provider use.
4. Enqueue with the active canonical claim ID, current fencing token and an
   idempotency key; inspect `status` before starting one worker. The runtime
   validates the claim, context and exact allowed paths. Use only read-only or
   runtime-created fixture worktrees; product workspace writes and external
   mutation are unavailable in v1.
5. Treat `waiting_approval` as a stop. Inspect the exact tool, payload digest
   and required authority. Only `human:<required-authority>` may decide; an
   agent, reviewer or operator cannot self-approve or accept risk.
6. After a crash or before a new Codex Desktop session takes over, run doctor
   and `npm run agent-runtime:brief -- --work VFBIZ-NNNN --target <workspace>`.
   Inspect the redacted event/checkpoint metadata before `resume`. Reconcile
   stale heartbeats; do not re-enqueue with a new idempotency key to bypass
   uncertain state.
7. Run `npm run agent-runtime:eval` and the changed-path gate against the
   program baseline. Stop if any backend, app, mobile, Drupal, infra or package
   path changed.
8. Runtime success is evidence only. Never mark the Git work item done, merge,
   deploy, migrate, release or delete a user worktree from this skill.
