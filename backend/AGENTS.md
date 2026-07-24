# Backend workspace instructions

## Scope

These rules apply to `backend/api` and `backend/ai`. Read the nearest nested
`AGENTS.md` before editing a runtime. Root policies and accepted ADRs remain
authoritative for cross-system decisions.

## Runtime boundary

- `api/` is the public/business authority. It authenticates users, authorizes
  objects, owns transactions and executes provider or AI tool side effects.
- `ai/` is private. It owns governed retrieval, inference, evaluation and tool
  proposals; it never becomes customer, payment, order or booking authority.
- Browser, Drupal, portal and mobile clients never call `ai/` directly.
- Data stores, migrations, environment variables and release gates are separate.

## Change routing

- Local, reversible change: stay in one runtime and run focused checks.
- Public/internal contract, identity, PII, migration, AI dataset/tool/release:
  treat as controlled and attach security/contract evidence.
- Changes touching both runtimes require one integration owner and an exclusive
  lease for the shared contract. Do not edit both contract representations in
  parallel.

## Shared invariants

- Never commit `.env`, secrets, PII, production data or raw provider responses.
- Fail closed when identity, source revision, authorization or AI evidence is
  absent.
- Vendor SDKs stay behind infrastructure adapters; business/domain code stays
  framework independent.
- Do not add a service, queue, framework or top-level module without an accepted
  boundary decision and a real consumer.
- A worker does not spawn another worker. Retry/review the same finding at most
  twice, and only with new evidence.

## Definition of done

- Required tests, static analysis, schema validation and migration review pass.
- Source/freshness and failure behavior are explicit.
- README/architecture is updated only when the boundary or operator workflow
  changed.
- The active Git work item receives concise evidence; chat history is not a
  source of truth.
