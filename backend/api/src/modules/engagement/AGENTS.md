# Customer Engagement

## Ownership

- Sở hữu conversation session/inbox/event, quota, support handoff, notification
  và AI gateway phía NestJS.
- Không sở hữu Trip Planner, LangGraph, retrieval, model routing hoặc AI release.

## Invariants

- Object authorization và profile scope được kiểm ở API trước khi gọi AI.
- Message dùng idempotency, sequence, OCC và fencing; không xử lý song song bằng
  cách ghi đè cùng conversation state.
- Handoff tồn tại bền vững ngoài WebSocket. Cancellation không xóa handoff.
- Hidden reasoning, raw provider/tool payload, bearer token và PII không vào event/log.
- AI chỉ đề xuất tool; V6 chỉ cho read-only execution đã authorize.

## Read when applicable

- `backend/api/docs/conversation-runtime.md`
- `backend/api/docs/ai-gateway-and-tools.md`
- `backend/api/docs/data-model.md`

## Verification

Chạy focused unit/E2E của engagement rồi `npm run verify:api`. Auth, PII,
Vision, public contract hoặc migration là controlled signal và cần đúng reviewer.
