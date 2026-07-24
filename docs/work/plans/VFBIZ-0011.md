---
id: plan-vfbiz-0011
title: ExecPlan Chatbot V6 và Dataset Factory
status: archived
owner_role: architect
scope: cross-system
when_to_read:
  - VFBIZ-0011
  - customer-chatbot-v6
tags:
  - chatbot
  - architecture
  - dataset
  - agents
revision: 2
review_date: 2026-08-23
supersedes: []
---

# Purpose

Thiết lập nguồn tri thức và control plane đủ chính xác để nhiều agent phát triển
Customer Chatbot V6 theo cùng ranh giới API/AI, đồng thời tạo Dataset Factory
fail-closed mà không đưa dữ liệu lớn hoặc dữ liệu chưa có quyền vào Git.

## Progress

- [x] 2026-07-23: Audit docs, instructions, skill, routing, tổ chức team và
  runtime foundation hiện tại.
- [x] Supersede nguồn staging cũ và xuất bản PRD, architecture, ADR Chatbot V6.
- [x] Bổ sung API/AI workspace docs và nested instructions.
- [x] Tách ownership, role và routing signal.
- [x] Tạo dataset contracts, source candidate register, fixture và validation.
- [x] Chuẩn hóa skill/adapter rồi chạy toàn bộ gate.

## Discoveries

- Async handoff hiện bị phân loại `bounded`, nên thiếu Security/Privacy review.
- Multimodal OCR chưa route qua API upload/RBAC và AI safety cùng lúc.
- `mobility-engagement` và `ai-platform-engineering` quá rộng để cấp path ownership.
- Một số NestJS module chỉ có `@Module({})` nhưng vẫn được import vào composition root.
- Active staging docs khiến Chatbot task nhận nhầm Trip Planner context.

## Decisions

- Chatbot V6 là current delivery focus; Account và Trip Planner vẫn là capability
  tương lai, không bị xóa khỏi roadmap.
- LangGraph internals thuộc AI docs; session, handoff, quota và signed gateway
  thuộc API docs.
- Registry/release chỉ có một writer; synthetic builder chỉ ghi candidate shard.
- Không có quyền sử dụng đã duyệt đồng nghĩa không được download.

## Implementation phases

1. Cập nhật product, cross-system architecture và ADR.
2. Phân bổ implementation knowledge vào API/AI workspace.
3. Cập nhật organization, roles, resolver và scenario tests.
4. Thêm machine-readable dataset contracts và deterministic validators.
5. Regenerate indexes/adapters, kiểm tra clean-code composition và chạy gates.

## Validation

- `npm run docs:check`
- `npm run adapters:check`
- `npm run governance:check`
- `npm run verify:api`
- `npm run verify:ai`
- Synthetic dataset positive/negative scenario commands được ghi trong skill.

## Rollback and recovery

Mọi thay đổi được giới hạn bởi VFBIZ-0011. Nếu một phase thất bại, revert đúng
paths của phase đó; không reset repository. Schema/manifest release mới chỉ là
governance contract nên chưa kích hoạt network, ingestion hoặc production runtime.

## Outcomes and retrospective

- Chatbot V6 có product/architecture/ADR active; staging Account/Trip cũ không
  còn được resolver chọn.
- Bảy team mới tách engagement, mobility, graph, model, knowledge, assurance và
  data governance; ba dataset role có authority/tool boundary khác nhau.
- Resolver vượt 33 scenario trên Codex/Claude/Gemini/generic, chọn nested
  instructions và không nạp toàn bộ docs.
- Dataset Factory có bảy JSON Schema, download gate, candidate validation,
  scalable near-dedup, manifest builder và realistic positive/negative tests.
- Không public dataset nào được download; rights vẫn fail closed.
- API gate đạt 44 test; AI gate đạt 25 test; governance/contract gate đạt.
- Production runtime, dataset approval và business content không nằm trong work
  item này và phải được mở thành bounded/controlled work riêng.
