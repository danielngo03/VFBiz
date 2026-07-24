---
id: plan-vfbiz-0003
title: FastAPI AI Platform rebuild plan
status: archived
owner_role: data-owner
scope: ai
when_to_read:
  - ai-rebuild
tags:
  - plan
  - fastapi
  - ai
revision: 1
review_date: 2026-07-22
supersedes: []
---

# FastAPI AI Platform Rebuild Implementation Plan

Use the current work item and nearest workspace instructions. This historical
plan does not authorize implementation by itself.

**Goal:** Replace `backend/ai` with a private, fail-closed FastAPI AI Platform organized by stable AI capabilities and ready for governed RAG, tool proposal and evaluation.

**Architecture:** One FastAPI deployable has an internal `/internal/v1` boundary. Capability packages own knowledge, inference, assistant, tooling, evaluation and governance; platform/infrastructure packages own cross-cutting adapters. API Platform remains the only customer-facing authority.

**Tech Stack:** Python 3.12+, FastAPI/Uvicorn, Pydantic Settings, SQLAlchemy asyncio, Alembic, asyncpg, pgvector, Redis, HTTPX, OpenTelemetry, Pytest, Ruff and Pyright.

## Global Constraints

- Preserve the old workspace in a timestamped Git-ignored backup before replacement.
- Top-level AI modules are exactly `knowledge`, `inference`, `assistant`, `tooling`, `evaluation`, `governance`.
- Provider/model names never become top-level modules.
- FastAPI is private; clients never call it directly.
- Public, customer-scoped and employee retrieval/policy are isolated.
- Factual output requires valid citation or refusal/handoff.
- Tools produce proposals only; API Platform authorizes and executes side effects.
- No LangChain, LlamaIndex, Celery or provider SDK in the foundation baseline.

---

## File map

```text
backend/ai/
├── app/
│   ├── main.py
│   ├── bootstrap/
│   ├── platform/{config,security,database,cache,observability,audit,health}/
│   ├── infrastructure/{model_providers,embedding_providers,vector_store,object_storage}/
│   └── modules/{knowledge,inference,assistant,tooling,evaluation,governance}/
├── migrations/{env.py,versions/}
├── tests/{unit,integration,contract,security,evaluation,architecture}/
├── .env.example
├── alembic.ini
├── pyproject.toml
└── uv.lock
```

### Task 1: Recoverable replacement and FastAPI scaffold

**Files:**
- Backup: `local-data/backend-rebuild/<timestamp>/ai/`
- Replace: `backend/ai/**`
- Create: `backend/ai/README.md`

**Interfaces:**
- Produces: `app.main:app` recognized by FastAPI CLI and uv project metadata.

- [ ] **Step 1: Create and verify backup manifest**

```bash
find backend/ai -type f -print0 | sort -z | xargs -0 shasum -a 256 > /tmp/vfbiz-ai-before.sha256
```

Expected: manifest contains `backend/ai/pyproject.toml`.

- [ ] **Step 2: Initialize clean uv project**

Create package `app`, `app/main.py`, Python 3.12 floor and explicit FastAPI entrypoint. Do not recreate `src/vfbiz_ai`.

```toml
[tool.fastapi]
entrypoint = "app.main:app"
```

- [ ] **Step 3: Write initial CLI smoke test**

```python
from app.main import app

def test_fastapi_entrypoint() -> None:
    assert app.title == "VFBiz AI Platform"
```

- [ ] **Step 4: Verify and commit**

```bash
uv sync --project backend/ai --extra test
uv run --directory backend/ai fastapi --help
uv run --directory backend/ai pytest tests/unit/test_entrypoint.py
git add backend/ai
git commit -m "build(ai): reinitialize FastAPI application"
```

### Task 2: Typed configuration and application bootstrap

**Files:**
- Create: `backend/ai/.env.example`
- Create: `backend/ai/app/platform/config/settings.py`
- Create: `backend/ai/app/bootstrap/application.py`
- Create: `backend/ai/app/bootstrap/lifespan.py`
- Modify: `backend/ai/app/main.py`
- Test: `backend/ai/tests/unit/platform/test_settings.py`

**Interfaces:**
- Produces: `Settings`, `get_settings()` and `create_application(settings)`.

- [ ] **Step 1: Write failing settings tests**

Test development defaults, missing staging database/Redis, enabled provider without pinned models, exposed docs outside local/test and invalid allowed hosts.

- [ ] **Step 2: Implement `BaseSettings` configuration**

Use `VFBIZ_AI_` prefix, frozen settings and explicit environment/model/provider literals. Production/staging fail before application startup when mandatory values are absent.

- [ ] **Step 3: Implement application factory and lifespan**

Docs/OpenAPI are disabled outside local/test. Lifespan initializes and closes only resources registered in the application container.

- [ ] **Step 4: Verify and commit**

```bash
uv run --directory backend/ai pytest tests/unit/platform/test_settings.py
uv run --directory backend/ai ruff check app tests
git add backend/ai
git commit -m "feat(ai): add typed fail-closed configuration"
```

### Task 3: Internal HTTP and security boundary

**Files:**
- Create: `backend/ai/app/api/internal_v1/router.py`
- Create: `backend/ai/app/platform/security/gateway_assertion.py`
- Create: `backend/ai/app/platform/security/request_context.py`
- Create: `backend/ai/app/platform/health/router.py`
- Test: `backend/ai/tests/security/test_internal_boundary.py`

**Interfaces:**
- Produces: `/internal/v1`, signed gateway assertion verifier, correlation context, liveness and readiness.

- [ ] **Step 1: Write negative boundary tests**

Reject missing assertion, wrong audience/issuer, expired assertion, untrusted host and client-supplied customer scope without signed evidence.

- [ ] **Step 2: Implement deny-by-default dependency**

Every internal business router depends on a verified `GatewayContext`. Only liveness is unauthenticated. No header directly grants an assistant profile or ACL.

- [ ] **Step 3: Add safe response middleware**

Set `no-store`, `nosniff`, `no-referrer`; never return tracebacks, prompts, retrieved chunks or provider details in error responses.

- [ ] **Step 4: Verify and commit**

```bash
uv run --directory backend/ai pytest tests/security/test_internal_boundary.py
git add backend/ai
git commit -m "feat(ai): establish private HTTP security boundary"
```

### Task 4: SQLAlchemy, pgvector and Alembic foundation

**Files:**
- Create: `backend/ai/app/platform/database/base.py`
- Create: `backend/ai/app/platform/database/session.py`
- Create: `backend/ai/app/platform/database/unit_of_work.py`
- Create: `backend/ai/app/modules/knowledge/infrastructure/models.py`
- Create: `backend/ai/app/modules/evaluation/infrastructure/models.py`
- Create: `backend/ai/app/modules/governance/infrastructure/models.py`
- Create: `backend/ai/migrations/env.py`
- Create: initial version under `backend/ai/migrations/versions/`.
- Test: `backend/ai/tests/architecture/test_persistence_models.py`

**Interfaces:**
- Produces: async session factory, unit-of-work port, SQLAlchemy metadata and Alembic migration authority.

- [ ] **Step 1: Write persistence architecture tests**

Assert SQLAlchemy models are confined to infrastructure, API schemas never inherit ORM models, AI tables use UUID/timestamp/source revision and vector dimension is explicit.

- [ ] **Step 2: Implement initial models**

Create source, chunk, embedding reference, dataset release, AI release, evaluation run and audit event. Store object keys/checksums, not source binaries or secrets.

- [ ] **Step 3: Configure Alembic and generate reviewed migration**

Migration creates `vector` extension only with migration identity, required tables/indexes and reversible local/test downgrade. Staging/production recovery remains forward-only.

- [ ] **Step 4: Verify**

```bash
uv run --directory backend/ai alembic check
uv run --directory backend/ai pytest tests/architecture/test_persistence_models.py
```

- [ ] **Step 5: Commit**

```bash
git add backend/ai
git commit -m "feat(ai): add governed pgvector persistence foundation"
```

### Task 5: Stable AI capability graph

**Files:**
- Create package roots for all six approved modules.
- Create `dependencies.py` only where composition exists.
- Create: `backend/ai/tests/architecture/test_module_boundaries.py`.

**Interfaces:**
- Produces: capability imports and composition rules independent of model provider.

- [ ] **Step 1: Write boundary tests**

Require exact module names; reject `openai`, `azure`, `chatbot`, `models`, `helpers` as top-level modules; reject framework/ORM imports in domain packages and cross-module infrastructure imports.

- [ ] **Step 2: Create minimal capability packages**

Do not create empty service/model files. Each package starts with its public protocol/types only when consumed.

- [ ] **Step 3: Verify and commit**

```bash
uv run --directory backend/ai pytest tests/architecture/test_module_boundaries.py
uv run --directory backend/ai pyright app
git add backend/ai
git commit -m "refactor(ai): establish stable capability boundaries"
```

### Task 6: Fail-closed answer contract

**Files:**
- Create: `backend/ai/app/modules/assistant/domain/models.py`
- Create: `backend/ai/app/modules/assistant/application/answer_service.py`
- Create: `backend/ai/app/modules/assistant/presentation/schemas.py`
- Create: `backend/ai/app/modules/assistant/presentation/router.py`
- Create ports under knowledge/inference/tooling.
- Test: `backend/ai/tests/contract/test_answer_contract.py`.
- Test: `backend/ai/tests/security/test_answer_policy.py`.

**Interfaces:**
- Produces: `POST /internal/v1/answers`, `AnswerRequest`, `GroundedAnswer`, `Citation` and refusal/handoff states.

- [ ] **Step 1: Write answer contract tests**

Test public/customer/employee profile vocabulary, citation revision/freshness, no-evidence refusal, cross-profile denial, invalid tool proposal and bounded conversation context.

- [ ] **Step 2: Implement provider-neutral ports**

Define protocols for retrieval, inference and tool proposal. Default adapters refuse because no approved release manifest exists.

- [ ] **Step 3: Implement stateless answer orchestration**

The service validates profile/policy, retrieves within ACL, requests generation, validates citations and returns grounded answer or refusal. It never stores customer chat history.

- [ ] **Step 4: Verify and commit**

```bash
uv run --directory backend/ai pytest tests/contract/test_answer_contract.py tests/security/test_answer_policy.py
git add backend/ai
git commit -m "feat(ai): add fail-closed internal answer contract"
```

### Task 7: Evaluation, observability and release gate

**Files:**
- Create evaluation release types and gate under `app/modules/evaluation/`.
- Create release manifest policy under `app/modules/governance/`.
- Create structured logging/OpenTelemetry under `app/platform/observability/`.
- Test: `tests/evaluation/test_release_gate.py`.
- Update: `backend/ai/README.md`, `backend/ai/docs/architecture.md`.

**Interfaces:**
- Produces: pinned release manifest, zero-leakage gate and observable cost/latency/citation metrics.

- [ ] **Step 1: Write release-gate tests**

Reject missing dataset owner/provenance, unpinned model/prompt/embedding/retriever/tool registry, ACL leakage, invalid citation rate and missing rollback/kill switch.

- [ ] **Step 2: Implement deterministic gate**

Gate output contains evidence IDs and failures; it never promotes or deploys a release by itself.

- [ ] **Step 3: Run full gate**

```bash
uv lock --project backend/ai --check
uv run --directory backend/ai ruff check app migrations tests
uv run --directory backend/ai pyright app
uv run --directory backend/ai pytest
uv run --directory backend/ai python -m compileall -q app migrations
```

Expected: all checks pass; no warning is silently converted into release approval.

- [ ] **Step 4: Record work-item evidence**

Move the AI rebuild item to `review` only after database, security and evaluation evidence is attached. Do not mark it `done` without staging integration and human AI release approval.

### Task 8: NestJS–FastAPI integration gate

**Files:**
- Modify under exclusive lease: `contracts/openapi/internal-v1.yaml`.
- Create: `backend/ai/tests/contract/test_openapi_compatibility.py`.
- Coordinate with: NestJS `engagement` infrastructure AI client.

**Interfaces:**
- Produces: provider-neutral internal answer contract shared by exactly two consumers.

- [ ] **Step 1: Validate generated FastAPI OpenAPI**

Assert `/internal/v1/answers` operation ID, request/response schema, service authentication, Problem Details and profile enum match the root contract.

- [ ] **Step 2: Run cross-backend contract tests**

```bash
npm run contracts:lint
uv run --directory backend/ai pytest tests/contract
npm run test:contract --workspace @vfbiz/api
```

- [ ] **Step 3: Record integration evidence and commit**

```bash
git add contracts backend/api backend/ai
git commit -m "test(backend): verify API and AI internal contract"
```
