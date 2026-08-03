# Dữ liệu, cache và offline

SQLite là structured cache/outbox, không phải system of record. Namespace:

```text
customer:environment:issuer:subject:market:schemaVersion
```

Mọi table có namespace trong primary key. Không query record chỉ bằng business
ID. Logout xóa cả cache_records, mutation_outbox và pending_payloads của partition;
schema migration phải giữ khả năng wipe khi deserialize thất bại.

Query cache memory mặc định stale sau 30 giây và GC sau 5 phút; persisted TTL sẽ
được quyết định theo data class trước khi bật hydration production. UI phân biệt
fresh, stale, unknown, offline, restricted, pending, verified và unverified.

Offline read được phép cho profile/garage đã phân loại và có “last updated”.
Offline mutation chỉ được queue nếu low-risk, có idempotency key và ETag khi bắt
buộc. Consent/privacy/security/session destructive action mặc định online-only.

Không lưu token, email, VIN, raw support content hoặc notification payload vào
log. SQLite encryption/OS backup policy cần Security/Privacy evidence trước dữ
liệu nhạy cảm production; foundation hiện không claim encrypted database.
