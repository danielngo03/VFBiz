---
id: ai-knowledge-release
title: Knowledge revision và atomic release
status: active
owner_role: data-owner
scope: ai
when_to_read:
  - knowledge-revision
  - knowledge-release
  - ai-retrieval
  - webhook
tags:
  - rag
  - revision
  - release
revision: 1
review_date: 2026-08-23
supersedes: []
---

# Knowledge revision và atomic release

## Source event

Drupal/approved source gửi webhook đã ký với event ID, source ID, source
revision, publish state và locator. API xác minh signature/replay rồi chuyển
event tới Knowledge Release control plane bằng internal assertion. Control
plane đặt revision barrier rồi tạo ingestion job tham chiếu source đã approved.
Chi tiết fetch/quarantine/scan/parse/chunk/embed thuộc
`knowledge-ingestion.md`. Poll/reconciliation là safety net; cron không phải
freshness mechanism chính.

## Revision lifecycle

```text
sync_requested -> ingesting -> candidate_ready -> evaluated -> ready -> active
                       \-> rejected
active -> superseded -> tombstoned
```

Ingestion chỉ báo candidate/evidence; nó không được chuyển state sang `active`.
Activation cập nhật một revision pointer atomic; query không trộn candidate với
active. Revision cũ chỉ tombstone sau activation thành công và rollback window
được bảo đảm.

## KnowledgeRevisionState

Mỗi domain/locale/profile có:

- active/candidate revision và source checksum;
- criticality, freshness deadline và sync started/deadline;
- transform/embedding/retriever revisions;
- failure state, rollback revision và tombstone lineage.

Critical domain như giá, safety, warranty, legal hoặc promotion đặt `syncing`
barrier ngay sau webhook được chấp nhận. Query chạm domain đó phải wait có timeout
hoặc trả typed `KNOWLEDGE_UPDATING`; không dùng revision cũ như fact hiện hành.
Non-critical domain có thể dùng last-known-good nếu freshness policy cho phép.

## Deletion và rollback

Withdraw/DSAR/source-rights revoke phải tombstone chunk, vector, cache, candidate
và derived dataset reference. Rollback chỉ tới revision vẫn có rights, ACL và
freshness phù hợp. Audit giữ metadata/hash cần thiết nhưng không giữ nội dung đã
bị yêu cầu xóa nếu không có legal hold.

## SLO và evidence

Theo dõi webhook-to-barrier, webhook-to-active, rejected revision, stale query,
rollback và delete completion. “Trong 30 giây” chỉ trở thành SLO sau benchmark
và capacity approval; trước đó là product target, không phải bảo đảm kỹ thuật.

## Kiểm thử

- Duplicate/out-of-order/replayed webhook.
- Query trước, trong và sau critical sync barrier.
- Ingestion/candidate failure giữ active pointer an toàn.
- Atomic activate và rollback khi cache/vector có replica lag.
- Withdraw/DSAR xóa đủ lineage và không tái xuất hiện sau reconciliation.
