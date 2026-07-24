@AGENTS.md

# Claude-specific mechanics

- Canonical skills are symlinked from `.claude/skills` to `.agents/skills`.
- Provider hooks may call deterministic repository guards but do not grant
  authority or replace CI.
