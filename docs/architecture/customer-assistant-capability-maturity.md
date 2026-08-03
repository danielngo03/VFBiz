---
id: customer-assistant-capability-maturity
title: Customer Assistant capability maturity
status: active
owner_role: engineering-lead
scope: cross-system
when_to_read:
  - capability-maturity
  - staging-readiness
tags:
  - customer-chatbot
  - capability-maturity
  - staging
revision: 1
review_date: 2026-08-29
supersedes: []
---

# Customer Assistant capability maturity

> Generated from the curated
> `customer-assistant-capability-maturity.json` register. The generator
> requires status-specific implementation, composition, verification-spec,
> blocker or human-authority probes. A verification-spec proves that a
> repository gate exists; observed execution evidence remains attached to the
> owning Work Item and release run. This report does not infer production
> approval.

| Capability | Maturity | Owner | Evidence-based interpretation |
| --- | --- | --- | --- |
| Durable Conversation Runtime | Implemented | `customer-engagement` | PostgreSQL inbox, OCC, fencing, cancellation, final commit and private dispatch are composed. |
| Public Chat API | Candidate | `customer-engagement` | Controllers and contracts exist, but production AppModule intentionally keeps them disabled. |
| LangGraph assistant runtime | Candidate | `ai-assistant-orchestration` | The graph composes a release-bound semantic router with deterministic fallback; immutable routing-slice evidence and factual acceptance remain incomplete. |
| Multi-turn task continuity | Candidate | `customer-engagement` | Task state is durable and vehicle-model candidates can be confirmed by the API-owned active catalog authority; broader slot families remain release-gated. |
| Knowledge Release and grounded retrieval | Candidate | `ai-knowledge-engineering` | Revision-coherent release and retrieval foundations exist; no approved VinFast source has passed staging acceptance. |
| Dataset Factory | Candidate | `ai-knowledge-engineering` | Registry, quarantine and release contracts exist; production worker orchestration and full quality authority remain incomplete. |
| AI Quality execution and evidence | Candidate | `ai-assurance` | Contracts and run registry exist; suite execution and EvidenceBundleAuthority are not composed. |
| Approved VinFast knowledge source | Human-blocked | `data-governance` | Requires real Content, Legal and Data Owner approval; agents cannot manufacture this evidence. |
| Customer Portal chat experience | Target-only | `customer-web-experience` | No production customer chat journey is composed; it remains gated by factual runtime acceptance. |
| Customer-scoped read-only tools | Target-only | `customer-engagement` | Vehicle profile and garage tools remain disabled until object authorization and evaluation gates pass. |

## Meaning of maturity

- **Implemented:** composed in the active runtime and covered by a repository
  verification specification. The latest observed pass/fail belongs to the
  owning Work Item or immutable release evidence, not this maturity register.
- **Candidate:** substantive implementation exists but one or more acceptance,
  composition or release gates remain.
- **Target-only:** architecture or contract intent exists without an accepted
  runtime consumer.
- **Human-blocked:** technical work cannot replace an explicit human authority
  decision or approved business artifact.

## Evidence probes

- **Durable Conversation Runtime:** `backend/api/src/app.module.ts`, `backend/api/src/modules/engagement/domain/runtime/conversation-task-context.ts`, `backend/api/test/integration/engagement/conversation-runtime.postgres-spec.ts`
- **Public Chat API:** `backend/api/src/modules/engagement/engagement.module.ts`, `backend/api/src/app.module.ts`
- **LangGraph assistant runtime:** `backend/ai/app/bootstrap/semantic_routing.py`, `backend/ai/.env.example`
- **Multi-turn task continuity:** `backend/api/src/modules/engagement/domain/runtime/conversation-task-context.ts`, `backend/ai/app/api/internal_v1/conversation_router.py`, `backend/api/src/integration/conversation/catalog-conversation-task-slot-authority.ts`, `backend/api/src/integration/conversation/catalog-conversation-task-slot-authority.ts`
- **Knowledge Release and grounded retrieval:** `backend/ai/app/modules/knowledge`, `backend/ai/docs/knowledge-ingestion.md`
- **Dataset Factory:** `backend/ai/app/modules/datasets`, `docs/work/items/VFBIZ-0185.md`
- **AI Quality execution and evidence:** `backend/ai/app/modules/evaluation/domain/run.py`, `docs/work/items/VFBIZ-0156.md`
- **Approved VinFast knowledge source:** `backend/ai/docs/knowledge-ingestion.md`, `backend/ai/docs/knowledge-ingestion.md`
- **Customer Portal chat experience:** `apps/customer-portal/src`, `backend/api/docs/conversation-runtime.md`
- **Customer-scoped read-only tools:** `backend/api/docs/ai-gateway-and-tools.md`, `backend/ai/app/bootstrap/release_runtime.py`

The generator validates every referenced path and marker and rejects a status
without its required evidence classes. Human reviewers still own the semantic
accuracy of each maturity classification.
