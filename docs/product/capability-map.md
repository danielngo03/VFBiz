---
id: capability-map
title: Bản đồ capability
status: active
owner_role: product-owner
scope: root
when_to_read:
  - discovery
  - new-capability
tags:
  - product
  - ownership
revision: 7
review_date: 2026-10-01
supersedes: []
---

# Bản đồ capability

| Domain                  | Capability dự kiến                                               | Workspace chính        |
| ----------------------- | ---------------------------------------------------------------- | ---------------------- |
| Content & brand         | Trang VI/EN, campaign, news, SEO, media, editorial workflow      | Drupal                 |
| Discovery               | Catalog, product detail, compare, search, location, 3D/360       | Drupal + API           |
| Conversion              | Quote, finance estimate, test drive và lead routing              | API                    |
| Customer account        | CIAM, profile, session, consent, DSAR và preference              | API + Customer Portal  |
| Customer web experience | Account, security, privacy và self-reported Garage journeys      | Customer Portal        |
| Ownership               | Xe, VIN, recall, service booking và notification                 | API + portal/mobile    |
| Commerce                | Wishlist, cart, deposit, checkout và order projection            | API                    |
| Workforce               | Cổng nhân sự, support, audit và nghiệp vụ nội bộ theo capability | Workforce Portal + API |
| Workforce authorization | Capability catalog, role động, assignment scope và maker-checker | API + Workforce Portal |
| Customer engagement     | Chat session, notification, support handoff và quota             | API                    |
| AI                      | Customer chatbot, owner/employee assistant và recommendation     | AI sau API             |
| AI Knowledge & Data     | Source lifecycle, RAG, dataset, evaluation và red-team           | AI                     |
| Platform                | Security, delivery, observability, recovery và cost control      | Infra                  |

Mỗi capability cần accountable owner, source of truth, data class, acceptance
criteria và exit gate trước implementation.

Account, Customer Data, Vehicle foundation và Customer Portal là capability
hiện active.
Customer Chatbot là wave kế tiếp và chỉ được đọc customer/vehicle data qua
authorized API tool. Trip Planner thuộc `mobility`; ba capability không dùng
chung owner chỉ vì cùng xuất hiện trên một giao diện.

Workforce Portal chỉ quản trị và trình bày entitlement. API là enforcement
authority và system of record cho role, assignment cùng organizational scope;
Keycloak chỉ xác thực identity, session và MFA.
