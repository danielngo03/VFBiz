# API contract và transport

Customer Mobile chỉ import endpoint types từ `@vfbiz/api-client`, được generate
từ `contracts/openapi/public-v1.yaml`. Không hand-copy DTO, không gọi Customer
Portal BFF và không thêm raw provider endpoint.

Transport tự thêm Bearer token và correlation ID; trả cả body, ETag và response
correlation ID. Non-2xx được map thành RFC Problem Details. UI xử lý riêng
401/403/409/412/429/5xx; 403 không được diễn giải thành “không tồn tại”.

Mutation tạo idempotency key trước lần gửi đầu và reuse cùng key khi retry chưa
biết kết quả. Profile/Garage update gửi `If-Match`; 412 tạo conflict state, không
silent overwrite. Blind retry bị cấm cho mutation không idempotent hoặc privileged.

Phase 1 resource allowlist: `/api/v1/me`, sessions/security, consents,
data-requests, vehicles và vehicle model projections. Assistant chỉ đi qua API
governance endpoint khi capability được mở; app không có AI provider SDK.

Contract CI kiểm generated drift và forbidden imports (`next`, server-only,
BFF contract, DB/Redis). Contract change controlled phải có backward compatibility
hoặc coordinated app minimum-version policy.
