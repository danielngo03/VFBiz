---
id: repository-blueprint
title: Repository blueprint
status: active
owner_role: architect
scope: root
when_to_read:
  - repository-change
  - cross-workspace
tags:
  - architecture
  - repository
revision: 5
review_date: 2026-10-01
supersedes: []
---

# Repository blueprint

Create source or documentation directories only for approved work with a real
consumer; do not add empty ceremony.

```text
VFBiz/
├── AGENTS.md                    # vendor-neutral agent contract
├── CLAUDE.md                    # thin provider adapter
├── .agents/                     # canonical roles and portable skills
├── .codex/ .claude/ .gemini/   # provider mechanics only
├── PLANS.md WORK.md             # plan standard and generated work view
├── docs/                        # cross-system product/governance/work truth
├── drupal/                      # Web Experience & CMS
├── backend/
│   ├── api/                     # Digital Platform modular monolith
│   └── ai/                      # private AI application
├── mobile/                      # React Native application
├── apps/
│   ├── customer-portal/         # Next.js customer BFF and account journeys
│   ├── workforce-portal/        # Next.js workforce BFF and internal UX
│   └── identity-theme/          # native Keycloak login/email theme JAR
├── packages/
│   └── design-tokens/           # generated tokens shared by three UI consumers
└── infra/                       # Platform & SRE
```

## Future implementation layout

- Each workspace owns its `src`, tests, migrations/config and local docs.
- Cross-system machine-readable contracts live in `contracts/`.
- Shared packages require at least two real consumers and an owner.
- Keycloak renders credential forms; portals only initiate OIDC and manage
  application-owned account journeys.
- Root tests cover only cross-system behavior; local tests stay with their code.
- Generated dependencies, datasets, binaries and build output are not committed.

Do not create a microservice, shared package, agent, skill or document merely to
mirror an organization chart. Add it only for a durable boundary or repeated need.
