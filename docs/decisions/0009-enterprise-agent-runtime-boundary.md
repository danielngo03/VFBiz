---
id: adr-0009
title: Enterprise agent runtime is an additive platform boundary
status: proposed
owner_role: architect
scope: cross-system
when_to_read:
  - agent-runtime
  - multi-agent
  - coding-agent
tags:
  - adr
  - agents
  - control-plane
revision: 1
review_date: 2026-08-30
supersedes: []
---

# ADR-0009: Enterprise agent runtime is an additive platform boundary

Date: 2026-07-30

## Context

VFBiz has strong provider-neutral governance and local control primitives but
does not have a process that schedules, resumes, observes and evaluates agent
runs. Putting that execution concern in API would mix it with public business
authority; putting it in AI would mix developer operations with ViVi inference
and data governance; putting it in infra would make deployment own application
workflow semantics.

## Decision

Create a private Node/TypeScript workspace at `agent-runtime`, owned by
Agent Platform. It composes the existing governance CLIs, a single-host SQLite
event/checkpoint store, OpenAI Agents SDK orchestration and sandbox executor
ports. It has no public endpoint and may not import product workspace internals.

The v1 candidate can read organization/work items and create fixture/sandbox
artifacts. Product writes, external mutation, release and production access are
absent. Runtime roles remain the existing canonical roles; teams and departments
are injected specialization, not persistent agent personalities.

## Alternatives

- Extend root scripts into a daemon: rejected because root governance tools
  should remain deterministic authorities, not own a long-lived application.
- Place the runtime in `backend/ai`: rejected because that service owns ViVi
  knowledge, inference and evaluation rather than enterprise coding operations.
- Place the runtime in `infra`: rejected because infra deploys and observes
  services but does not own their workflow state machine.
- Start distributed with PostgreSQL/Temporal: deferred until a multi-host or
  shared-inbox requirement has measured evidence.

## Consequences

- A new durable repository boundary and npm workspace are introduced.
- SQLite is explicitly local and replaceable through a `RunStore` port.
- Git work items and existing claims/leases remain canonical, preventing a
  second approval or ownership system.
- Runtime/provider integrations can be disabled without affecting product code.
- Deployment, strong human identity and multi-machine coordination require a
  later controlled program.

## Approval

Human decision owner: `architect`, with security, data and engineering review.
The user explicitly requested implementation of this local candidate on
2026-07-30. This ADR remains `proposed` and does not grant production release or
risk-acceptance authority.
