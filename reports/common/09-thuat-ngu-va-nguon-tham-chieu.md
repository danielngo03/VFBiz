---
report_id: glossary-and-source-map
title: Thuật ngữ và nguồn tham chiếu
audience: executive-and-technical
report_scope: target-architecture
owner_role: architect
source_documents:
  - ../../docs/README.md
  - ../../docs/architecture/system-context.md
  - ../../docs/governance/security-data-ai.md
review_date: 2026-10-24
---

# Thuật ngữ và nguồn tham chiếu

> **Kiến trúc đích, không phản ánh trạng thái triển khai.**

## Thuật ngữ

| Thuật ngữ          | Ý nghĩa trong VFBiz                                             |
| ------------------ | --------------------------------------------------------------- |
| API Platform       | NestJS application giữ business authority và public contract    |
| AI Platform        | Private FastAPI application cho LangGraph, RAG và evaluation    |
| BFF                | Backend for Frontend giữ web token/session server-side          |
| Capability         | Hành động nghiệp vụ nguyên tử của workforce                     |
| Customer Garage    | Danh sách vehicle reference của khách hàng                      |
| DSAR               | Yêu cầu truy cập/xuất/xóa dữ liệu của data subject              |
| EVSE               | Thiết bị cung cấp điện cho một hoặc nhiều connector             |
| Handoff            | Chuyển phiên hỗ trợ từ AI sang nhân viên có trạng thái bền vững |
| Identity realm     | Không gian Keycloak tách customer và workforce identity         |
| Knowledge revision | Phiên bản knowledge candidate/active có thể rollback            |
| LangGraph          | State-machine orchestration cho conversation AI                 |
| Maker-checker      | Người đề xuất và người phê duyệt phải khác nhau                 |
| Model Mesh         | Lớp routing/fallback model theo task, risk, cost và policy      |
| OIDC               | Giao thức đăng nhập dựa trên OAuth 2.0                          |
| OCC                | Optimistic Concurrency Control chống lost update                |
| PostGIS            | PostgreSQL extension cho dữ liệu và truy vấn geospatial         |
| Projection         | Bản sao dữ liệu có source, revision và freshness                |
| RAG                | Retrieval-Augmented Generation từ evidence đã duyệt             |
| Reserve SOC        | Mức pin tối thiểu phải giữ theo planning policy                 |
| System of Record   | Nguồn có thẩm quyền cuối cùng cho một loại dữ liệu              |
| Tool proposal      | Đề xuất có schema từ model, chưa phải business action           |
| WIP                | Công việc đang thực hiện, không đồng nghĩa đã nghiệm thu        |

## Nguồn Product

- [Tầm nhìn sản phẩm](../../docs/product/vision.md)
- [Bản đồ capability](../../docs/product/capability-map.md)
- [Roadmap](../../docs/product/roadmap.md)
- [Nền tảng tài khoản và dữ liệu xe](../../docs/product/customer-account-and-vehicle.md)
- [Customer Portal](../../docs/product/customer-portal.md)
- [Customer Chatbot](../../docs/product/customer-chatbot.md)

## Nguồn Architecture

- [System context](../../docs/architecture/system-context.md)
- [Repository blueprint](../../docs/architecture/repository-blueprint.md)
- [Identity, Customer và Vehicle foundation](../../docs/architecture/identity-customer-vehicle-foundation.md)
- [Customer Chatbot V6](../../docs/architecture/customer-chatbot-v6.md)

## ADR

- [ADR 0002 — Customer Chatbot V6](../../docs/decisions/0002-customer-chatbot-v6.md)
- [ADR 0003 — Account/Vehicle trước Chatbot](../../docs/decisions/0003-account-vehicle-before-chatbot-runtime.md)
- [ADR 0004 — Dynamic Workforce Authorization](../../docs/decisions/0004-dynamic-workforce-authorization.md)
- [ADR 0005 — Customer Portal BFF và DAL](../../docs/decisions/0005-customer-portal-bff-and-dal.md)
- [ADR 0006 — Keycloak Identity Experience](../../docs/decisions/0006-enterprise-keycloak-identity-experience.md)
- [ADR 0007 — EV Route & Charging Planner](../../docs/decisions/0007-ev-route-and-charging-planner.md)

## Nguồn Governance

- [Security, Data và AI baseline](../../docs/governance/security-data-ai.md)
- [Open-source, Brand và IP](../../docs/governance/open-source-brand-ip.md)
- [Workforce Authorization threat model](../../docs/governance/workforce-authorization-threat-model.md)
- [Delivery và authority](../../docs/operating-model/delivery-and-authority.md)
- [Multi-agent và review](../../docs/operating-model/multi-agent-and-review.md)
- [Context và handoff](../../docs/operating-model/context-and-handoff.md)

## Workspace implementation references

- [API architecture](../../backend/api/docs/architecture.md)
- [API data model](../../backend/api/docs/data-model.md)
- [Conversation Runtime](../../backend/api/docs/conversation-runtime.md)
- [AI Gateway và tools](../../backend/api/docs/ai-gateway-and-tools.md)
- [AI architecture](../../backend/ai/docs/architecture.md)
- [Conversation Graph](../../backend/ai/docs/conversation-graph.md)
- [Knowledge ingestion](../../backend/ai/docs/knowledge-ingestion.md)
- [Knowledge release](../../backend/ai/docs/knowledge-release.md)
- [Evaluation và release](../../backend/ai/docs/evaluation-and-release.md)
- [Customer Portal architecture](../../apps/customer-portal/docs/architecture.md)
- [Workforce Portal architecture](../../apps/workforce-portal/docs/architecture.md)
- [Identity Theme architecture](../../apps/identity-theme/docs/architecture.md)

## Quy tắc sử dụng

- Khi report và canonical source khác nhau, canonical source thắng.
- Khi ADR và implementation khác nhau, coi implementation chưa đạt decision;
  không sửa report để hợp thức hóa drift.
- Implementation status chỉ lấy từ work item, test evidence và release record.
- External link, dataset hoặc provider term cần được kiểm tra lại tại thời điểm
  ra quyết định vì có thể thay đổi theo thời gian.
