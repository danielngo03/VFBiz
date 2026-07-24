# Customer portal workspace instructions

Root `AGENTS.md` applies. This workspace is owned by Customer Web Experience.

- Protect authenticated data by subject and session; NestJS remains the
  business authorization authority.
- Use generated API types. Never expose provider token to browser code, storage,
  HTML or logs.
- Server Components use the server-only DAL directly. Use Server Actions for
  form mutations and Route Handlers only for browser-specific auth/BFF needs.
- Accessibility and failure states are part of every customer journey.
- Authentication, token vault, session, PII and privacy paths are controlled;
  read `docs/architecture.md` for those changes.
- Read `docs/design-system.md` for visual primitives and
  `docs/experience-and-accessibility.md` for journey behavior.
- When changing Next.js behavior, inspect the version-matched documentation in
  `node_modules/next/dist/docs/`; do not rely on recalled APIs from another
  Next.js version.
- Run the smallest relevant checks; auth/BFF changes require unit, Redis
  integration and production build checks.

Do not create catch-all `common`, `helpers` or `utils` folders, or a shared
design package without a second approved consumer.
