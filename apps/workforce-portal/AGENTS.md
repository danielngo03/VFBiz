# Workforce Portal workspace instructions

Read root `AGENTS.md` and this file. Read `README.md` for scope.

- This Next.js application is a workforce BFF and user interface, not an
  authorization authority or system of record.
- Use Server Components by default. Add Client Components only at the smallest
  interaction boundary.
- Keep access/refresh tokens in the server-side token vault. Never put tokens
  or trusted capability state in browser storage or client bundles.
- UI visibility is advisory. NestJS must authorize every protected operation.
- Auth, authorization, exports, customer data and bulk actions are controlled.
- Small presentational changes may use fast lane when behavior is unchanged.
- Read `docs/architecture.md` for BFF/session changes and
  `docs/authorization-ux.md` for capability-driven UI changes.
- Read `docs/testing.md` before changing test taxonomy or browser gates.
- Run `npm run typecheck`, `npm test` and, when a route changes,
  `npm run test:e2e`.
