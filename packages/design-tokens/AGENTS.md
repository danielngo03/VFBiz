# Design token workspace

Read root `AGENTS.md`.

- This package owns portable visual tokens, not React components or brand assets.
- Keep core values neutral until Brand/Legal approval exists.
- Customer and Workforce may override semantic roles, never primitive names.
- Run `npm test` after token changes; generated files must match source hashes.
- Do not add remote fonts, URLs, tracking or executable code.
