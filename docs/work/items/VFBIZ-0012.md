---
id: VFBIZ-0012
title: Chốt nền tảng Account và dữ liệu xe trước Chatbot
status: done
mode: controlled
priority: P0
owner_team: architecture-integration
accountable_role: architect
primary_workspace: root
affected_workspaces:
  - root
  - api
allowed_paths:
  - docs
  - backend/api/docs
  - backend/api/AGENTS.md
  - tests/governance
  - tools
  - WORK.md
depends_on: []
controlled_signals:
  - architecture
  - authentication
  - customer-profile
  - customer-garage
  - customer-data
  - vehicle-catalog
  - vehicle-ownership
  - data-governance
exclusive_resources:
  - architecture-boundaries
required_checks:
  - npm run governance:check
  - npm run docs:check
revision: 5
review_date: "2026-08-23"
updated_at: "2026-07-23T05:33:26.584Z"
---

# Outcome

Chốt foundation Account, Customer Profile, Vehicle Catalog và Customer Garage
thành nguồn product/architecture/data ownership thống nhất, để implementation
NestJS tiếp theo không tự đoán field, system of record hoặc authorization.

## Constraints

- Chưa triển khai Chatbot runtime, LangGraph, RAG hoặc dataset ingestion.
- Keycloak/CIAM sở hữu credential, MFA và identity verification; API không lưu
  password, recovery secret hoặc MFA seed.
- VinFast catalog, ownership và VIN chưa có provider production được phê duyệt;
  staging chỉ dùng projection/fixture synthetic có source revision.
- Không tạo microservice, module hoặc bảng cho capability chưa có use case.
- ADR mới chỉ thay đổi delivery order; không làm mất kiến trúc Chatbot V6 đã duyệt.

## Done when

- Product acceptance cho Account và Vehicle foundation được viết bằng tiếng Việt.
- ADR xác định delivery order, bounded context và system-of-record rõ ràng.
- Roadmap đặt Account/Vehicle trước Conversation Runtime/AI.
- API docs mô tả dữ liệu phải lưu, dữ liệu bị cấm, lifecycle, retention và
  object authorization.
- Resolver route đúng identity, profile/consent, catalog và garage mà không nạp
  tài liệu AI/Trip không liên quan.
- Documentation index và governance gate đạt.

## Checkpoint

- Base revision: `1310d7529dbc9a275b7fcef1b66b55e2b285b858`.
- Ba audit lane read-only đang kiểm Account domain, Vehicle domain và
  Identity/Security; chỉ orchestrator được tích hợp thay đổi.
- Exact next action: xuất bản product/architecture/ADR và API workspace docs,
  sau đó chạy routing scenarios.

## Evidence

- [x] `npm run governance:check` — 37 provider-neutral scenarios đạt, bao gồm
  profile, garage, catalog và ownership routing.
- [x] `npm run docs:check` — index hiện hành được sinh từ 48 durable documents.

Residual gates: staging Account chưa được mở cho tới khi Security/Privacy duyệt
BFF/CIAM contract và retention matrix. DMS/PIM/ownership provider chưa được giả
lập thành production authority.

### review — 2026-07-23T05:33:26.312Z

Product, architecture, API data boundaries và routing đã được audit độc lập; 37 scenarios đạt.

### done — 2026-07-23T05:33:26.584Z

Foundation Account/Vehicle đã chốt; runtime implementation được tách thành work item riêng.
