# AI entrypoint cho Customer

Assistant là capability-gated route, không phải provider integration. Luồng duy
nhất được phép là Mobile -> NestJS API authority -> governed AI Platform. API
chịu trách nhiệm authz, consent, tool policy, grounding, audit và rate limit.

Foundation đặt `assistantEnabled: false`. Route vẫn có để kiểm navigation nhưng
hiển thị closed state. Khi mở, app còn phải kiểm server capability theo subject,
market, app version và incident kill switch; public config không đủ quyền bật.

Không gửi toàn bộ profile/garage/session vào prompt. Request context dùng schema
explicit, data minimization và user-visible purpose. Tool proposal không được UI
trình bày là action đã thực thi; mutation cần confirmation, API authority và
reconciliation riêng.

Streaming, conversation persistence, citation UI, feedback, safety state,
human handoff và deletion/retention là work item khác. App không tích hợp model
SDK, vector DB, prompt template hoặc API key.
