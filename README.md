# VFBiz

VFBiz là nền tảng số ngành ô tô, được xây dựng để kết nối trải nghiệm khách
hàng, vận hành nội bộ, dữ liệu xe, quản trị tri thức và các capability AI trong
một hệ sinh thái thống nhất.

Dự án không chỉ là một website hoặc chatbot. VFBiz bao gồm public web, cổng
khách hàng, cổng nhân sự, Identity Platform, Backend API, AI Platform và các
khả năng mở rộng như Customer Chatbot và Lập kế hoạch hành trình EV.

> **Trạng thái:** Repository đang ở giai đoạn xây dựng và nghiệm thu nền tảng.
> Không nên xem các capability trong roadmap là đã production-ready.

![Kiến trúc tổng thể VFBiz](reports/common/images/01-system-landscape.svg)

_VFBiz tách rõ các kênh trải nghiệm, business authority, AI Platform, dữ liệu và
hệ thống bên ngoài._

## Mục tiêu

- Cung cấp trải nghiệm nhất quán cho khách hàng trên public web, Portal và
  mobile.
- Quản lý Account, Customer, Customer Garage và dữ liệu xe theo nguồn có thẩm
  quyền.
- Hỗ trợ lực lượng nhân sự qua Workforce Portal với phân quyền động và audit.
- Cho phép cập nhật tri thức doanh nghiệp mà không cần nhân sự truy cập trực
  tiếp cloud console hoặc database.
- Xây dựng Customer Chatbot có citation, refusal và human handoff.
- Tính toán hành trình EV bằng dữ liệu và thuật toán deterministic thay vì để
  LLM tự suy đoán.
- Giữ hệ thống độc lập với model/provider và có thể phát triển bằng nhiều coding
  agent mà không phụ thuộc vào lịch sử hội thoại.

## Thành phần sản phẩm

| Thành phần          | Đối tượng                    | Vai trò                                                           |
| ------------------- | ---------------------------- | ----------------------------------------------------------------- |
| Drupal Public Web   | Khách truy cập               | Content, SEO, discovery và điểm vào các hành trình số             |
| Customer Portal     | Khách hàng đã xác thực       | Hồ sơ, bảo mật, consent, dữ liệu cá nhân và Customer Garage       |
| Mobile              | Khách hàng                   | Trải nghiệm native, offline và hành trình di chuyển trong roadmap |
| Workforce Portal    | Nhân sự                      | Customer Support, dữ liệu sản phẩm, phân quyền, approval và audit |
| Identity Experience | Customer và Workforce        | Login, registration, MFA, passkey, recovery và email identity     |
| API Platform        | Tất cả client được phê duyệt | Business authority, authorization, transaction và integration     |
| AI Platform         | API Platform                 | RAG, LangGraph, model policy, evaluation và tool proposal         |
| EV Journey Platform | Customer channels và Chatbot | Tìm trạm và lập kế hoạch hành trình EV trong roadmap              |

## Kiến trúc

VFBiz được tổ chức thành ba plane:

1. **Experience Plane:** Drupal, Customer Portal, Workforce Portal, Mobile và
   Identity Experience.
2. **Runtime Data Plane:** NestJS API, FastAPI AI, các business context,
   database và provider adapter.
3. **Control & Assurance Plane:** workflow quản trị, audit, observability,
   FinOps, dataset/prompt release và human approval.

![Các runtime container của VFBiz](reports/common/images/03-runtime-containers.svg)

### Nguyên tắc chính

- **Authority trước automation:** UI và AI không thay thế business authority.
- **Deny by default:** đăng nhập thành công không đồng nghĩa có quyền thực hiện
  mọi hành động.
- **Evidence trước câu trả lời:** thông tin factual phải có nguồn hoặc hệ thống
  từ chối trả lời.
- **Deterministic cho con số và mutation:** giá, chính sách, SOC và transaction
  đến từ code/tool được kiểm soát.
- **Provider-neutral:** Keycloak, model, cloud và bản đồ nằm sau contract/adapter.
- **Revision-aware:** data, policy, prompt, model và release đều có version.
- **Human accountability:** con người duyệt product scope, security, privacy,
  architecture và production release.

## Cấu trúc repository

```text
VFBiz/
├── apps/
│   ├── customer-portal/       # Next.js BFF và hành trình Customer
│   ├── workforce-portal/      # Next.js BFF và nghiệp vụ Workforce
│   └── identity-theme/        # Keycloak login/email theme
├── backend/
│   ├── api/                   # NestJS API Platform
│   └── ai/                    # FastAPI AI Platform nội bộ
├── contracts/                 # OpenAPI, AI và governance schemas
├── docs/                      # Product, architecture, ADR, governance và work
├── drupal/                    # Public web, CMS, SEO và editorial workflow
├── infra/                     # Local runtime, Keycloak, delivery và SRE
├── mobile/                    # Mobile boundary; runtime thuộc roadmap
├── packages/
│   ├── api-client/            # Generated Customer/Public API client
│   ├── workforce-api-client/  # Generated Workforce API client
│   ├── portal-session-core/   # Session primitives dùng chung cho Portal
│   └── design-tokens/         # Semantic design tokens dùng chung
├── reports/                   # Báo cáo tổng quan và báo cáo theo tuần
├── tools/                     # Work, agent, docs, contract và report tooling
├── AGENTS.md                  # Chỉ dẫn portable cho coding agent
├── PLANS.md                   # Chuẩn ExecPlan
└── WORK.md                    # View trạng thái công việc được sinh tự động
```

Mỗi workspace có ownership, instructions, tài liệu và quality gate riêng. Root
chỉ giữ tri thức xuyên hệ thống; chi tiết implementation nằm trong workspace sở
hữu capability đó.

## Công nghệ chính

| Khu vực                   | Công nghệ                                                             |
| ------------------------- | --------------------------------------------------------------------- |
| API Platform              | NestJS 11, Fastify, Prisma, PostgreSQL 17 và PostGIS                  |
| AI Platform               | FastAPI, Pydantic, SQLAlchemy, Alembic, pgvector và Redis             |
| Customer/Workforce Portal | Next.js 16, React 19, TypeScript và server-side BFF                   |
| Identity                  | Keycloak 26.7, OIDC, PKCE, MFA và native theme JAR                    |
| Public Web                | Drupal và DDEV                                                        |
| Contract                  | OpenAPI, JSON Schema và generated TypeScript SDK                      |
| Quality                   | ESLint, TypeScript, Jest, Vitest, Playwright, Pytest, Ruff và Pyright |
| Delivery governance       | Git-native work item, context resolver, claim/lease và CI gates       |

## Trạng thái hiện tại

### Nền tảng đã được xây dựng

- Repository đa-workspace và Multi-Agent Operating System độc lập provider.
- NestJS/FastAPI foundation, persistence, migration, health check và contract.
- Keycloak customer/workforce realm, OIDC, session security và Identity Theme.
- Account, Customer, Customer Garage và governed Vehicle Catalog foundation.
- Dynamic Workforce Authorization theo capability, role và organizational
  scope.
- Next.js foundation cho Customer Portal và Workforce Portal.
- AI data contract, dataset governance, evaluation và release gate.
- Bộ báo cáo kiến trúc tổng thể trong
  [reports/common](reports/common/README.md).

### Đang hoàn thiện và nghiệm thu

- Customer Portal: profile, security, privacy, session và Garage journeys.
- Workforce Portal: role, assignment, approval, Customer Support và audit.
- Browser E2E cho toàn bộ login, MFA, logout và authorization flow.
- Reconciliation với provider và dữ liệu Product có provenance.

### Roadmap tiếp theo

- Customer Chatbot runtime, LangGraph, RAG và Knowledge Release.
- Lập kế hoạch hành trình EV, dữ liệu trạm sạc và energy estimation.
- Mobile experience, commerce, service và ownership integrations.

Trạng thái canonical của từng hạng mục nằm trong [WORK.md](WORK.md), không nằm
trong README hoặc bộ nhớ của agent.

## Bắt đầu phát triển

### Yêu cầu

- Node.js `22+`.
- npm `11.8.0`.
- Python `3.12` và [uv](https://docs.astral.sh/uv/) cho AI Platform.
- PostgreSQL 17 + PostGIS và Redis nếu chạy native local.
- DDEV/Docker khi phát triển Drupal hoặc cần dependency containerized.

VFBiz ưu tiên **local-first**. Docker Compose chỉ là lựa chọn thay thế khi máy
chưa có dependency hoặc cần môi trường tích hợp gần với CI.

### Cài dependency

```bash
git clone <repository-url>
cd VFBiz
npm install
uv sync --project backend/ai --group test
```

Không commit `.env`. Tạo cấu hình local từ các file `.env.example` trong từng
workspace và sử dụng secret riêng cho máy phát triển.

### Khởi động API Platform

```bash
cp backend/api/.env.example backend/api/.env
npm run db:local:bootstrap --workspace @vfbiz/api
npm run prisma:generate --workspace @vfbiz/api
npm run start:dev --workspace @vfbiz/api
```

API chạy mặc định tại `http://127.0.0.1:8000`:

- Customer Scalar: `http://127.0.0.1:8000/reference/customer`
- Workforce Scalar: `http://127.0.0.1:8000/reference/workforce`
- Swagger UI: `http://127.0.0.1:8000/api-docs`

### Khởi động AI Platform

```bash
cp backend/ai/.env.example backend/ai/.env
uv run --directory backend/ai alembic upgrade head
uv run --directory backend/ai fastapi dev --host 127.0.0.1 --port 8888
```

AI Platform mặc định fail closed khi chưa có provider và AI release được phê
duyệt. Client không được gọi trực tiếp service này. Các runbook chứa cấu hình
hạ tầng cá nhân được quản lý ngoài repository công khai.

### Khởi động Portal

```bash
npm run dev --workspace @vfbiz/customer-portal
npm run dev --workspace @vfbiz/workforce-portal
```

| Service          | Địa chỉ mặc định        |
| ---------------- | ----------------------- |
| Customer Portal  | `http://127.0.0.1:3001` |
| Workforce Portal | `http://127.0.0.1:3002` |
| Keycloak         | `http://127.0.0.1:8080` |
| API Platform     | `http://127.0.0.1:8000` |
| AI Platform      | `http://127.0.0.1:8888` |
| PostgreSQL API   | `127.0.0.1:5434`        |
| Redis            | `127.0.0.1:6379`        |

Hướng dẫn dependency local và Keycloak đầy đủ nằm tại
[infra/local/README.md](infra/local/README.md) và
[infra/local/keycloak/README.md](infra/local/keycloak/README.md).

## Kiểm tra chất lượng

```bash
# Governance, agent routing, work item và contracts
npm run verify:governance

# NestJS API
npm run verify:api

# Customer Portal và Workforce Portal
npm run verify:apps

# FastAPI AI
npm run verify:ai

# Drupal
npm run verify:drupal

# Toàn bộ repository
npm run verify
```

Một quality gate đạt không đồng nghĩa sản phẩm đã được release. Code-complete,
acceptance-complete, released và outcome-validated là các trạng thái khác nhau.

## Làm việc với coding agent

VFBiz dùng cùng contract cho Codex, Claude, Gemini và generic provider:

1. Đọc [AGENTS.md](AGENTS.md).
2. Xác định workspace sở hữu thay đổi.
3. Resolve context thay vì đọc toàn bộ repository:

   ```bash
   npm run agent:context -- --stage delivery --path backend/api
   ```

4. Tạo work item cho công việc `bounded` trở lên.
5. Chỉ sửa `allowed_paths`; dùng claim/lease cho controlled hoặc parallel work.
6. Chạy quality gate gần nhất và ghi evidence vào work item.

Worker không được tạo worker khác, tự phê duyệt risk hoặc tiếp tục retry vô hạn.
Tối đa ba writer có thể chạy song song khi path hoàn toàn tách biệt.

## Tài liệu

- [Tóm tắt điều hành](reports/common/01-tom-tat-dieu-hanh.md)
- [Sản phẩm và trải nghiệm](reports/common/02-san-pham-va-trai-nghiem.md)
- [Kiến trúc hệ thống](reports/common/03-kien-truc-he-thong.md)
- [Identity, Data và System of Record](reports/common/04-identity-data-va-system-of-record.md)
- [Customer Chatbot và Knowledge Platform](reports/common/05-customer-chatbot-va-knowledge-platform.md)
- [Lập kế hoạch hành trình EV](reports/common/06-ev-journey-planner.md)
- [Security, Governance và vận hành](reports/common/07-security-governance-va-van-hanh.md)
- [Tổ chức và lộ trình](reports/common/08-to-chuc-va-lo-trinh-phat-trien.md)
- [Document index](docs/INDEX.md)
- [Work overview](WORK.md)

`docs/`, ADR, contracts và code là nguồn sự thật. `reports/` là lớp tổng hợp
phục vụ người đọc; chat history và provider memory không phải nguồn sự thật.

## Bảo mật và dữ liệu

- Không commit secret, token, password, production PII, customer conversation,
  raw VIN, proprietary dataset hoặc asset chưa có quyền sử dụng.
- Chỉ dùng synthetic/versioned data trong local và test.
- Báo cáo lỗ hổng theo [SECURITY.md](SECURITY.md); không công khai dữ liệu nhạy
  cảm trong issue hoặc pull request.
- Mọi thay đổi authentication, authorization, PII, public contract, migration,
  AI hoặc production đều là controlled change và cần review phù hợp.

## Đóng góp

Trước khi thay đổi code:

- kiểm tra [WORK.md](WORK.md) để tránh trùng lane;
- đọc root và nearest `AGENTS.md`;
- không sửa file ngoài phạm vi work item;
- không trộn refactor không liên quan vào cùng thay đổi;
- không tuyên bố release hoặc chấp nhận residual risk thay cho human owner.

Repository hiện chưa công bố license nguồn mở. Việc sử dụng code, dữ liệu và
asset phải tuân theo quyền sở hữu và phê duyệt của dự án.
