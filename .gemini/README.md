# Gemini CLI adapter

`settings.json` makes hierarchical `AGENTS.md` the context filename, so root and
workspace instructions are reused instead of copied into `GEMINI.md`. Gemini also
recognizes `.agents/skills` as a workspace skill location. Gemini agents are thin,
isolated-context adapters to the canonical roles; they do not own product truth or
provider-specific copies of the operating model.
