# Identity Theme workspace

Read root `AGENTS.md`.

- Keycloak owns every credential form and authentication action.
- This workspace may consume generated design tokens but never portal runtime code.
- Prefer theme inheritance, CSS and messages; do not copy upstream FreeMarker pages.
- No remote font, analytics, CDN, tracking or unapproved brand asset.
- FreeMarker, scripts, dependencies and realm selection are controlled changes.
- Run `npm run verify` and the local Keycloak checks before handoff.
