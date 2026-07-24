---
id: documentation-router
title: Documentation router
status: active
owner_role: engineering-lead
scope: root
when_to_read:
  - documentation
  - context
tags:
  - docs
  - routing
revision: 1
review_date: 2026-09-01
supersedes: []
---

# Documentation router

Do not recursively preload `docs/`. Run
`npm run agent:context -- --path <target>` and read only returned headings.

| Need | Canonical location |
| --- | --- |
| Product outcome and roadmap | `product/` |
| Cross-system boundaries | `architecture/` |
| Delivery, authority, agents and context | `operating-model/` |
| Security, data, AI, license and brand | `governance/` |
| Accepted technical decisions | `decisions/` |
| Current work and ExecPlans | `work/` |
| API, AI, Drupal or client implementation | Nearest workspace `docs/` |

`docs/INDEX.md` and the machine catalog are generated from document
frontmatter. Only `active` documents are selected automatically; proposed,
superseded and archived material requires an explicit request.
