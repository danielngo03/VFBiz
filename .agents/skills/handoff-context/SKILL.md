---
name: handoff-context
description: Create or validate a compact VFBiz context capsule and run report before compaction, interruption, worktree transfer or provider handoff; use to resume from durable evidence without rereading the whole repository.
---

# Handoff context

1. Finish the current atomic action; never compact an incomplete edit/migration.
2. Record the capsule fields in `docs/operating-model/context-and-handoff.md`
   within 1,500 tokens.
3. Include source revisions and links, not copied documents or raw logs.
4. Record exit state, evidence, blockers and one exact next action.
5. On a fresh Codex session, run `npm run agent-runtime:brief -- --work
   VFBIZ-NNNN --target <workspace>`. The brief may expose hashes, bounded work
   excerpts and artifact references; it must not decrypt checkpoints or expose
   raw event payloads.
6. Validate Git/work-item revisions and reload only sources reported stale by
   the brief/context resolver. If the old context cache is gone, resolve a full
   fresh context and mark the previous runtime authority stale.
7. Discard stale claims; never rely on chat or provider memory as authority.
