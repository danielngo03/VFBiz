# VFBiz AI Platform

Private FastAPI service for governed RAG, inference, tool proposals and AI
evaluation. It is not a public chatbot backend: API Platform authenticates and
authorizes every customer/workforce request before issuing a signed internal
assertion.

## Architecture at a glance

```text
API Platform
  -> signed /internal/v1 request
  -> assistant policy/profile check
  -> ACL-aware knowledge retrieval
  -> provider-neutral inference
  -> citation validation
  -> grounded answer | refusal | handoff
```

Stable capability ownership is documented in [AGENTS.md](./AGENTS.md). Provider
implementations live under `app/infrastructure`; provider names never enter the
domain or public internal contract.

AI Platform Engineering builds candidates and may run deterministic evaluation,
but an independent evaluator verifies the evidence. Automated gates never approve
or deploy: the applicable Data, Privacy and Security owners retain risk authority,
and the Release Owner alone authorizes promotion or rollback. Runtime boundaries
are in [architecture](./docs/architecture.md); abuse controls and containment are
in [safety and abuse](./docs/safety-and-abuse.md).

## Local setup

```bash
cp backend/ai/.env.example backend/ai/.env
uv sync --project backend/ai --group test
uv run --directory backend/ai fastapi dev --host 127.0.0.1 --port 8888
```

The default provider is `disabled`: without an approved release and adapters the
answer service refuses. Do not place model/provider keys in Git.

Local-first mặc định dùng service host trên máy:

- AI Platform: `127.0.0.1:8888`
- API gateway issuer: `http://127.0.0.1:8000`
- PostgreSQL: `127.0.0.1:5432`, database `vfbiz_ai`
- Redis: `127.0.0.1:6379`, logical database `2`

Docker chỉ cần dùng khi muốn chạy một dependency chưa cài trên máy hoặc cần
replay môi trường tích hợp giống CI.

## Migrations

```bash
uv run --directory backend/ai alembic upgrade head
uv run --directory backend/ai alembic downgrade -1  # local/test recovery only
```

The initial migration creates the `vector` extension and governed knowledge,
dataset, AI release, evaluation and audit tables. Production recovery is
forward-only even though local/test downgrade is available.

## Quality gate

```bash
uv lock --project backend/ai --check
uv run --directory backend/ai ruff check app migrations tests
uv run --directory backend/ai pyright app
uv run --directory backend/ai pytest
uv run --directory backend/ai python -m compileall -q app migrations
```

Current foundation includes private gateway authentication, safe response
headers, explicit capabilities, pgvector/Alembic persistence, a fail-closed
grounded-answer service and deterministic AI release gate. Released pgvector
retrieval is runtime-composed. Vertex generation and embedding are now wired
through the provider-neutral release factory using ADC/workload identity, but
remain disabled until a matching release manifest, approval evidence and cost
policy are resolved; standalone smoke evidence is not product-runtime evidence.

## Capability readiness

| Capability | Implemented | Runtime-wired | DB-tested | Cloud-deployed | Authority-accepted | Release-active |
| --- | --- | --- | --- | --- | --- | --- |
| Assistant orchestration | yes | yes | yes | no | no | no |
| Knowledge retrieval | yes | yes | yes | no | no | no |
| GCP intake and Document AI reconciliation | yes | isolated worker | yes | no | no | no |
| Vertex generation and embedding | candidate | release-gated factory | adapter tests | no | no | no |
| Evaluation evidence authority | yes | yes | yes | not applicable | public-diagnostic only | no |
| Dataset and Golden qualification | 1,000-case candidate | no | deterministic tests | no | no; adjudication 0/1,000 | no |
| Authenticated staging Chat | candidate | no | partial | no | no | no |

“Implemented” never implies deployment, authority acceptance or release. The
active work items and sealed evidence remain the source of truth for each later
column.
