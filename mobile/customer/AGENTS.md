# Customer Mobile instructions

Read root `AGENTS.md` and this file. `/mobile` is only a filesystem container and
does not provide inherited product or runtime instructions.

- Customer product/runtime truth lives in this app and `docs/`; do not write it
  at `/mobile` container level or into Workforce paths.
- Route files compose screens/providers only. Business rules live in `domain/`,
  `features/`, `platform/` or `state/` and must be testable outside routing.
- Import API types from `@vfbiz/api-client`; never duplicate endpoint DTOs.
- Namespace persisted data by environment, issuer, subject, market and schema.
- Auth, deep links, storage, permissions, app config, dependencies and releases
  are controlled changes. OTA and sensitive permissions default to disabled.
- CNG owns native generation. Do not commit `ios/` or `android/` without an
  accepted ADR changing ownership.
- Preserve Dynamic Type, screen-reader order, reduced motion and 44-point touch
  targets in every reusable component.
- Start with `npm run agent:context -- --path mobile/customer` or the active
  Customer work item. Use only the returned headings and at most two skills.
- Customer changes are owned by `mobile-experience`. Coordinate through the work
  item with Product Management, Identity Experience, Architecture & Integration,
  API Foundation and Reliability Engineering; agents exchange evidence, not
  authority or free-form hidden chat.
- Auth, PII/offline, public contract, native dependency and release require an
  independent reviewer/risk reviewer. Agent findings are recorded in the work
  item/ExecPlan; only named human roles accept scope, architecture, risk/release.
- Do not create role-specific runtime agents (`ios-agent`, `android-agent`,
  `expo-agent`) as new authorities. Use existing explorer, implementer,
  reviewer-verifier, risk-reviewer and integrator roles with a bounded objective.
