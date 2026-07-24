---
id: VFBIZ-0049
title: DSAR execution adapters và reconciliation
status: proposed
mode: controlled
priority: P0
owner_team: customer-product
accountable_role: privacy-owner
primary_workspace: api
affected_workspaces:
  - api
  - ai
  - infra
allowed_paths:
  - backend/api
  - backend/ai
  - infra
  - contracts
  - docs/work/items
  - WORK.md
depends_on:
  - VFBIZ-0032
controlled_signals:
  - customer-data
  - pii
  - dsar
exclusive_resources:
  - database-migration
  - public-contract
required_checks:
  - npm run verify:api
  - npm run verify:ai
  - npm run governance:check
revision: 1
review_date: "2026-08-23"
---

# Outcome

DSAR export/delete chạy bất đồng bộ qua adapter thật của từng system, retry hữu
hạn và chỉ kết thúc khi mọi target bắt buộc có evidence hoặc legal-hold decision
được đúng human authority phê duyệt.

## Constraints

- Không adapter nào được trả noop success.
- Privacy/Legal Owner phải duyệt retention, execution deadline, recent-auth,
  legal-hold authority/purpose/expiry và backup erasure semantics trước `ready`.
- Identity mapping bị xóa/tombstone cuối cùng trong delete plan.
- Export artifact ở private object storage, URL ký ngắn hạn và không ghi PII
  vào audit/outbox/error.
- Worker dùng lease + fencing token, retry hữu hạn và operator queue.

## Done when

- API, CIAM, AI, object storage/cache và telemetry có adapter thật cùng contract
  test; unavailable target fail closed.
- Aggregation xử lý partial failure, permanent failure và legal-hold expiry.
- Export artifact download yêu cầu recent authentication và one-time/short TTL.
- Delete lineage chứng minh target completion mà không giữ dữ liệu đã xóa.
- Crash/retry sau từng phase không làm mất subject mapping hoặc chạy side effect
  hai lần.

## Checkpoint

- Exact next action: Privacy/Legal/Data Owner chốt policy IDs và owner của từng
  target; sau đó Architecture định nghĩa executor port cùng adapter contract.

## Evidence

- [ ] `npm run verify:api` — add evidence reference
- [ ] `npm run verify:ai` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
