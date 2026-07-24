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
5. On resume, validate Git/work-item revisions and reload only stale sources.
6. Discard stale claims; never rely on chat or provider memory as authority.
