# Observability

Mỗi event có app/environment, version, build, runtime fingerprint, platform và
correlation ID khi liên quan API. Không ghi raw token, email, VIN, display name,
search/prompt/support content hoặc full response body.

Signal tối thiểu: cold/warm start, auth start/cancel/callback/exchange/refresh/
logout-wipe, route failure, API status/problem type, offline transition, SQLite
migration/wipe, update/build identity và handled/unhandled error.

Metrics release cần crash-free session, ANR, cold start, auth success/failure,
401/403/409/412/429/5xx, cache-wipe failure và navigation smoke. Không tạo user
fingerprint từ device metadata. Sampling/retention/region cần Privacy approval.

Foundation chỉ có scrubbed development logger và release diagnostics. Sentry/EAS
Observe admission là controlled dependency change; DSN là public routing value,
không phải lý do gửi PII. Source map upload credential chỉ ở CI secret store.
