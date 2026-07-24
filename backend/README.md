# Backend VFBiz

Backend được tổ chức thành hai runtime có trust boundary riêng, không phải hai
cách viết cùng một backend.

| Runtime | Stack | Authority | Database |
|---|---|---|---|
| `api/` | NestJS 11, Fastify, Prisma | `/api/v1`, identity projection, authorization, transaction, side effect | PostgreSQL/PostGIS |
| `ai/` | FastAPI, SQLAlchemy, Alembic | retrieval, inference, tool proposal, evaluation | PostgreSQL/pgvector |

Client chỉ gọi API Platform. AI Platform chỉ nhận internal request đã được API
xác thực và giới hạn scope. Một model không được tự cấp quyền hoặc thực thi
side effect.

## Bắt đầu theo loại thay đổi

- API/domain/migration: đọc `api/AGENTS.md`, `api/docs/architecture.md` và
  `api/docs/data-model.md`; dùng skill `evolve-backend-capability`.
- RAG/model/tool/evaluation: đọc `ai/AGENTS.md`, `ai/docs/architecture.md` và
  `ai/docs/security-profiles-and-release.md`.
- Thay đổi cả hai runtime: cần Integration Owner, contract revision và lease
  cho tài nguyên dùng chung; không để hai writer sửa contract song song.

Không đọc recursive toàn bộ `docs/`. Chạy `npm run context:resolve -- --stage
delivery --path <target>` từ root để lấy context manifest tối thiểu.
