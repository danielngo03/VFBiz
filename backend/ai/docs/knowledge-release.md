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
revision: 4
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

Webhook/API chỉ xác nhận job đã được tạo; không chờ parse/OCR/embed. Mỗi delivery
pin event ID và source revision. Delivery lỗi transient được retry hữu hạn;
permanent failure hoặc vượt attempt limit đi DLQ có operator-visible reason,
retention và replay audit.

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

Control plane persist ba boundary riêng:

- `KnowledgeRelease` là manifest bất biến pin source-set hash, parser/transform,
  chunker, embedding dimension/revision, retriever, policy, index checksum,
  effective/freshness window và evaluation evidence.
- `KnowledgeRevisionPointer` là authority duy nhất cho active release của đúng
  `(domain, locale, assistant profile, ACL namespace)`.
- `RevisionBarrier` dùng generation tăng đơn điệu; activation cũ không thể xóa
  barrier mới hơn.

Source Register v2 là read-only authority. Candidate, approval và activation
đều revalidate approved purpose `knowledge`, exact ACL, public classification,
rights, retention, deletion fence, checksum và registry document hash. Snapshot
được ký hash bao gồm enum `source_type`, locator không chứa credential, owner,
custodian, toàn bộ license/commercial-use/derivative/redistribution/access
condition/evidence/legal-review, retention policy/duration và approval evidence.
Legacy source row thiếu metadata v2 bị từ chối; hệ thống không tự backfill
approval.

## Atomic activation

Activation khóa release, pointer và source projection trong cùng PostgreSQL
transaction, sau đó:

1. CAS release version, pointer version và barrier generation;
2. xác minh maker khác checker, MFA/capability và source snapshot chưa đổi;
3. chuyển active cũ thành `superseded` và candidate thành `active`;
4. cập nhật pointer, clear đúng barrier generation;
5. ghi append-only transition và transactional outbox.

Partial unique index bảo đảm tối đa một active release cho một scope. Cache và
vector không tham gia transaction; retrieval phải pin release ID/pointer version,
còn outbox chỉ phát invalidation/reconciliation. Telemetry sink không nằm trong
main flow. Raw source, signed URL, token và PII không đi vào transition/outbox.

Rollback là một governed activation mới: target phải được revalidate rights,
ACL, freshness, deletion fence và embedding/retriever compatibility. Pointer
không được rewind trực tiếp.

Mọi command pin idempotency key theo aggregate và operation. PostgreSQL advisory
transaction lock tuần tự hóa duplicate command trước CAS; transition lưu replay
result đã bỏ source locator để retry đồng thời không chạy lại side effect. Mọi
transaction nhiều aggregate khóa toàn bộ release theo UUID, rồi revision pointer,
rồi source projection. Pointer ban đầu được tạo bằng `ON CONFLICT DO NOTHING`
rồi khóa lại để tránh unique race và deadlock.

## Deletion và rollback

Withdraw/DSAR/source-rights revoke phải tombstone chunk, vector, cache, candidate
và derived dataset reference. Rollback chỉ tới revision vẫn có rights, ACL và
freshness phù hợp. Audit giữ metadata/hash cần thiết nhưng không giữ nội dung đã
bị yêu cầu xóa nếu không có legal hold.

Barrier chỉ mở cho release `ready`, source snapshot còn hợp lệ và deadline nằm
trong 15 phút kế tiếp. Candidate đang giữ critical barrier không thể bị candidate
khác ghi đè. Rollback bị từ chối khi còn candidate hoặc barrier không `clear`, và
chỉ phục hồi artifact có embedding dimension/revision cùng retriever revision với
runtime active.

Emergency withdrawal của release đang active hoặc đang giữ candidate barrier
atomically xóa pointer liên quan, tăng barrier generation và đặt barrier
`blocked` trước khi release thành `tombstoned`. Release và outbox cùng phát đúng
generation mới. Retrieval không được dùng previous release như fallback khi
barrier đang blocked; operator phải activate một candidate đã duyệt để mở lại
domain. Mutation chỉ nhận reason code giới hạn 80 ký tự; ghi chú vận hành/PII
không đi vào transition hoặc outbox.

DLQ và failed artifact cũng nằm trong deletion lineage. Replay không được dùng
source revision đã bị withdraw, hết rights hoặc supersede bởi emergency
withdrawal.

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
- DLQ replay giữ idempotency, không activate nhầm revision cũ và không giữ source
  content quá retention.
