---
report_id: common-report-index
title: Bộ báo cáo kiến trúc đích VFBiz
audience: executive-and-technical
report_scope: target-architecture
owner_role: architect
source_documents:
  - ../../docs/product/vision.md
  - ../../docs/product/capability-map.md
  - ../../docs/architecture/system-context.md
  - ../../docs/architecture/repository-blueprint.md
review_date: 2026-10-24
---

# Bộ báo cáo kiến trúc đích VFBiz

> **Kiến trúc đích, không phản ánh trạng thái triển khai.** Trạng thái thực tế
> được quản lý trong `docs/work/items`, tests và release evidence.

## Mục đích

Bộ báo cáo này trình bày VFBiz như một hệ sinh thái sản phẩm số thống nhất cho
khách hàng và nhân sự: public web, tài khoản, mobile, quản trị nội bộ, Customer
Chatbot, Knowledge Platform và Lập kế hoạch hành trình EV.

Đây là lớp trình bày dành cho người đọc. Nguồn sự thật vẫn là:

- `docs/product`: outcome, audience, capability và roadmap;
- `docs/architecture`: ranh giới xuyên hệ thống;
- `docs/decisions`: quyết định kiến trúc đã chấp nhận;
- `docs/governance`: security, privacy, data, AI và quyền sử dụng;
- `contracts`: giao diện machine-readable;
- workspace docs và code: implementation truth.

Report không được dùng để suy ra rằng một capability đã code-complete,
production-ready hoặc outcome-validated.

## Lộ trình đọc

### Dành cho lãnh đạo

1. [Tóm tắt điều hành](01-tom-tat-dieu-hanh.md)
2. [Sản phẩm và trải nghiệm](02-san-pham-va-trai-nghiem.md)
3. [Tổ chức và lộ trình phát triển](08-to-chuc-va-lo-trinh-phat-trien.md)

### Dành cho kiến trúc sư và kỹ sư

1. [Kiến trúc hệ thống](03-kien-truc-he-thong.md)
2. [Identity, Data và System of Record](04-identity-data-va-system-of-record.md)
3. [Customer Chatbot và Knowledge Platform](05-customer-chatbot-va-knowledge-platform.md)
4. [EV Journey Planner](06-ev-journey-planner.md)
5. [Security, Governance và vận hành](07-security-governance-va-van-hanh.md)
6. [Thuật ngữ và nguồn tham chiếu](09-thuat-ngu-va-nguon-tham-chieu.md)

## Mục lục hình

| Hình                                                                | Nội dung                                          |
| ------------------------------------------------------------------- | ------------------------------------------------- |
| [System landscape](images/01-system-landscape.svg)                  | Actors, channels, platform và enterprise systems  |
| [Experience channels](images/02-experience-channels.svg)            | Customer, Workforce và Identity journeys          |
| [Runtime containers](images/03-runtime-containers.svg)              | API, AI, data và event boundaries                 |
| [Identity và data ownership](images/04-identity-data-ownership.svg) | Realm, session và system-of-record                |
| [Chatbot runtime](images/05-chatbot-runtime.svg)                    | Conversation Runtime, LangGraph và Model Mesh     |
| [Knowledge release](images/06-knowledge-release.svg)                | Upload, quarantine, approval và atomic activation |
| [EV Planner](images/07-ev-planner.svg)                              | Route, energy, charging và plan result            |
| [Security assurance](images/08-security-assurance.svg)              | Cross-cutting controls và human gates             |
| [Capability roadmap](images/09-capability-roadmap.svg)              | Thứ tự xây dựng capability                        |

## Quy ước

- Tiếng Việt được dùng cho nội dung; thuật ngữ kỹ thuật giữ nguyên khi dịch làm
  giảm độ chính xác.
- Mũi tên liền biểu diễn runtime call/data flow; mũi tên đứt biểu diễn control,
  approval hoặc telemetry.
- “Authority” là nơi có quyền quyết định; “projection” là bản sao có nguồn,
  revision và freshness.
- Mỗi hình có Mermaid source trong `images/source`.
- `source-manifest.json` pin hash của canonical sources để CI phát hiện report
  cần được review lại khi Product docs, ADR hoặc workspace docs thay đổi.
- Không dùng logo, font hoặc asset thương hiệu khi chưa có Brand/Legal approval.
