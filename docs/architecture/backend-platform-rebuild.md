---
id: backend-platform-rebuild
title: Quyết định lịch sử về Backend Platform
status: superseded
owner_role: architect
scope: backend
when_to_read:
  - architecture-history
tags:
  - architecture
  - backend
revision: 2
review_date: 2026-08-23
supersedes: []
---

# Quyết định lịch sử về Backend Platform

Ngày 22/07/2026, VFBiz tái khởi tạo hai application có ranh giới độc lập:

- `backend/api`: NestJS/Fastify modular monolith, sở hữu public API,
  authorization, transactional state và integration orchestration.
- `backend/ai`: FastAPI modular application, sở hữu private AI orchestration,
  retrieval, model routing, evaluation và governed tool proposal.

Quyết định tách boundary vẫn còn hiệu lực. Chi tiết implementation đã được
chuyển về `backend/api/docs/` và `backend/ai/docs/`; tài liệu này không còn được
resolver chọn cho delivery mới để tránh sao chép module map và library list dễ
stale. Kiến trúc xuyên hệ thống hiện tại nằm trong
`docs/architecture/customer-chatbot-v6.md` và ADR 0002.
