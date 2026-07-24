# Claude Code adapter

Root and nested `CLAUDE.md` import canonical `AGENTS.md`. Provider agent files
set Claude-specific tool restrictions and point to canonical role definitions.
`.claude/skills` links to `.agents/skills` so skill content has one source. Do not
preload more than two skills into a subagent because the full skill bodies consume
its context. Skills, roles and business rules remain canonical outside this adapter.
