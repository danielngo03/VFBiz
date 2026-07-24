# Codex adapter

Codex reads hierarchical `AGENTS.md` and canonical `.agents/skills` directly.
Project agent TOMLs only set discovery and tool/sandbox mechanics. They must point
back to `.agents/roles` and must not duplicate business rules. Provider-native
skills are optional accelerators; the repository must still work from canonical
instructions when they are unavailable. Start Codex in the owning workspace and
use `npm run context:resolve -- --path <target>` before loading extra documents.
