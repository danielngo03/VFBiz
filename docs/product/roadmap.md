---
id: product-roadmap
title: Roadmap sản phẩm
status: active
owner_role: product-owner
scope: root
when_to_read:
  - portfolio
  - release-planning
tags:
  - product
  - roadmap
revision: 7
review_date: 2026-09-01
supersedes:
  - enterprise-portfolio
---

# Roadmap sản phẩm

Roadmap mô tả thứ tự, không tự cấp quyền code. Một wave chỉ bắt đầu khi entry
criteria, human owner và vendor dependency được phê duyệt.

## Wave 0 — Account và Vehicle foundation (current)

- CIAM/OIDC boundary, account lifecycle, session, profile, consent và DSAR.
- Structured model/variant projection có source, revision và freshness.
- Customer Garage với self-reported lifecycle và VIN privacy.
- Customer Portal hoàn thiện account, security, privacy và Garage journey bằng
  Next.js BFF; catalog chỉ phục vụ chọn model/variant trong Garage.
- DMS/PIM adapter chỉ bắt đầu khi có provider, contract và owner thật.

## Wave 1 — Customer Chatbot V6

- Conversation Runtime, LangGraph, RAG revision barrier và read-only tools.
- Evaluation-first Dataset Factory, Source Register, golden/red-team suite.
- Handoff bền vững, Model Mesh, PromptOps và release evidence.
- Workforce authorization foundation được triển khai độc lập để quản trị
  support, knowledge release và audit theo least privilege.

## Wave 2 — Public discovery và conversion

- Drupal CMS/SSR, VI/EN, SEO, navigation, media và design system.
- Catalog/product detail, compare, location, finance estimate, lead và test drive.

## Wave 3 — Commerce, ownership và workforce operations

- DMS/VIN verification, recall, service, mobile và notification.
- Deposit/checkout/order projection và workforce operations.

## Wave 4 — AI mở rộng và trải nghiệm nâng cao

- Owner assistant và employee assistant có profile/ACL tách biệt.
- Side-effecting tools chỉ mở sau authorization, confirmation và audit.
- Trip Planner, 3D/360 và recommendation chỉ mở khi data/SLA được phê duyệt.

Implementation status lấy từ active `docs/work/items/`, không lấy từ roadmap.
Roadmap item chưa cam kết cho tới khi Product Owner phê duyệt và có current work item.
