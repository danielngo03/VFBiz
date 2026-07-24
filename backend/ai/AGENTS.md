# VFBiz AI Platform instructions

## Mission and authority
This FastAPI service is private and fail closed. It owns governed knowledge
ingestion/retrieval, inference orchestration, tool proposals, evaluation and AI
release policy. API Platform remains identity, authorization and side-effect
authority. No client calls this service directly.

## Stable capabilities
Only these directories may exist under `app/modules`:

- `knowledge`: source lifecycle, chunks, ACL-aware retrieval and tombstones.
- `inference`: provider-neutral generation/embedding ports and routing policy.
- `assistant`: answer orchestration and profile-specific behavior.
- `tooling`: versioned tool proposal registry and schema validation.
- `evaluation`: offline/security/regression suites and deterministic gates.
- `governance`: dataset/release manifests, approvals and kill-switch policy.

Provider/model names, `chatbot`, a single screen or a temporary feature never
become top-level modules. Provider adapters live under `app/infrastructure`.

## Internal layering
Use `domain`, `application`, `presentation` and `infrastructure` only when a
capability has code in that layer. Domain/application types cannot depend on
FastAPI, SQLAlchemy, Redis, HTTPX or a model SDK. Presentation maps Pydantic
schemas to domain/application types; SQLAlchemy models remain infrastructure.

## AI safety invariants
- Factual answer has approved evidence, citation, source revision and freshness;
  otherwise refuse or hand off.
- ACL filtering occurs before retrieval/ranking and is rechecked before response.
- Public, authenticated-customer and employee profiles never share an unscoped
  retrieval namespace, prompt or tool authority.
- Tools create proposals only. API authorizes, confirms, executes and audits any
  side effect.
- Fine-tuning is not a data freshness, authorization or missing-source fix.
- No customer chat becomes training data by default.
- A release gate never promotes/deploys its own candidate.

## Team boundary và assurance

- Assistant Orchestration sở hữu LangGraph/tool proposal; Model Platform sở hữu
  inference/provider; Knowledge Engineering sở hữu RAG/revision/candidate shard;
  AI Assurance tạo evidence; Data Governance giữ source/rights/release decision.
- Builder có thể chạy deterministic evaluation nhưng không tự chấp nhận evidence.
- Independent reviewer xác minh suite/artifact; Data, Privacy, Legal và Security
  owners quyết định trong human authority của họ.
- Automated gates produce evidence, not approval. The Release Owner alone
  authorizes promotion, rollback and production release.

## Persistence and migration

- AI PostgreSQL/pgvector is separate from API PostgreSQL.
- Alembic is migration authority; vector dimension and model/embedding revision
  are explicit.
- Store object keys/checksums and redacted text, not source binaries, secrets,
  unredacted PII or raw provider payloads.

## Focused references

- Boundary/graph: `docs/architecture.md`, `docs/conversation-graph.md`.
- Knowledge/dataset/serving: `docs/knowledge-release.md`,
  `docs/knowledge-ingestion.md`, `docs/dataset-engineering.md`, `docs/inference-serving.md`.
- Safety/root policy: `docs/safety-and-abuse.md`,
  `../../docs/governance/security-data-ai.md`.

Use the resolver; do not preload release material for a local formatting change.

## Commands

```bash
uv run --directory backend/ai ruff check app migrations tests
uv run --directory backend/ai pyright app
uv run --directory backend/ai pytest
uv run --directory backend/ai alembic upgrade head --sql
```

Do not mark an AI release ready without independent evaluation, zero ACL/PII
leakage, citation/refusal evidence, pinned revisions, rollback and kill switch.
