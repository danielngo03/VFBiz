# AI Assistant Orchestration

## Ownership

- Sở hữu LangGraph State Machine, Supervisor, typed state, clarification,
  bounded reflection, interrupt và checkpoint migration.
- Không authorize customer, execute business tool hoặc truy cập API PostgreSQL.

## Layering

Module này có `graph/` bên cạnh 4 layer chuẩn: đây là layer framework-binding
riêng cho LangGraph (state, nodes, builder, runtime, migrations,
serialization), tách khỏi `infrastructure/` (Postgres adapter cho application
port). `domain`/`application` không được import `graph` hoặc `infrastructure`
— `tests/unit/assistant/test_architecture_boundaries.py` enforce việc này.

## Invariants

- Global Entities và Active Task State tách biệt; chỉ confirmed entity được promote.
- Một operation tối đa ba attempt; authorization/safety/rights failure không retry.
- Model output không tăng scope trong signed assertion.
- Vision/OCR là untrusted observation và phải qua injection policy.
- Không stream chain-of-thought; chỉ trả typed status/answer/refusal/handoff.

## Read when applicable

- `backend/ai/docs/conversation-graph.md`
- `backend/ai/docs/safety-and-abuse.md`
- `docs/architecture/customer-chatbot-v6.md`

## Verification

Chạy focused graph/policy tests rồi `npm run verify:ai`. Thay state schema,
profile hoặc tool contract là controlled change.
