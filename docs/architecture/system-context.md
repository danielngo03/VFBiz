---
id: system-context
title: Bối cảnh hệ thống
status: active
owner_role: architect
scope: root
when_to_read:
  - cross-system
  - architecture
tags:
  - architecture
  - boundaries
revision: 7
review_date: 2026-10-01
supersedes: []
---

# Bối cảnh hệ thống

```text
Khách hàng / nhân sự
        |
 CDN/WAF and identity boundaries
        |
 Drupal public web ----- Customer/mobile/workforce clients
        |                         |
        +------ API Platform -----+
                     |
       enterprise systems and AI Platform
```

## Ownership

- Drupal: public SSR, CMS, SEO, editorial workflow và web image metadata.
- API: `/api/v1`, caller authorization, transaction, integration orchestration,
  public projection và conversation runtime.
- AI: private LangGraph, retrieval, model policy, evaluation và governed tool proposal.
- Customer Portal: Next.js BFF giữ token server-side và cung cấp account,
  security, privacy cùng Garage experience. Server DAL gọi API Platform trực
  tiếp; browser chỉ gọi same-origin auth/BFF surface.
- Mobile: native client tương lai dùng Authorization Code + PKCE và secure
  native storage; không dùng chung session cookie của web.
- Client: presentation, local state và secure session; không là system of record.
- Workforce Portal: Next.js BFF và authorization UX; browser chỉ giữ opaque
  session, còn API quyết định capability, organizational scope và object access.
- External systems: CIAM, CRM/DMS, PIM/ERP, payment và fulfillment authority.

Trust boundary, data flow và runtime choice cần accepted ADR trước implementation.
Sơ đồ này không phải deployment design.

## Bốn plane của Customer AI và EV Mobility

- **Experience:** Drupal, Customer Portal, Mobile và Workforce Portal.
- **Application & Integration:** NestJS giữ identity/object authorization,
  conversation, handoff, tool enforcement, Mobility và enterprise adapters.
- **AI Runtime:** FastAPI giữ LangGraph execution, governed retrieval, Model
  Mesh và evaluation runtime; không trở thành business authority.
- **Control & Assurance:** Knowledge Release, PromptOps, dataset, security,
  privacy, audit, FinOps và release evidence.

PostgreSQL/PostGIS, AI PostgreSQL/pgvector, object storage, Redis và Pub/Sub
được gắn với authority/retention cụ thể; chúng không tạo một “data layer” chung
cho phép API và AI đọc chéo tùy ý. Security, privacy, availability và cost là
control xuyên mọi plane, không phải bước kiểm tra cuối.

Current implementation order và Identity/Vehicle system-of-record được chốt tại
ADR 0003. CIAM sở hữu credential/MFA; PIM/ERP sở hữu catalog facts; DMS/CRM sở
hữu ownership verification. API chỉ lưu business state hoặc governed projection
cần thiết cho authorization và customer journey.

Đối với nhân sự, Keycloak sở hữu authentication và MFA nhưng không sở hữu
business authorization. API PostgreSQL lưu capability definition, role,
assignment, organizational scope và entitlement revision. UI ẩn action để hỗ
trợ UX; mọi request vẫn bị API kiểm tra deny-by-default.

Public resource contract `/api/v1` và browser-specific Customer BFF contract là
hai contract độc lập. Việc chúng cùng được triển khai trong repository không
làm browser auth route trở thành public resource API.
