# AI Knowledge Engineering

## Ownership

- Sở hữu Source Register implementation, ingestion, chunking, embedding,
  retrieval, revision activation và tombstone.
- Không chấp nhận license, release dataset hoặc tự tạo factual VinFast source.

## Invariants

- Public/customer/employee namespace và cache key tách biệt; ACL lọc trước ranking.
- Critical revision activate atomic; query không trộn candidate với active.
- Evaluation/red-team split không đi vào knowledge/training.
- Download bị chặn khi Source Register chưa có approved rights/purpose.
- Registry/release cần exclusive lease; builder chỉ ghi candidate shard riêng.

## Read when applicable

- `backend/ai/docs/knowledge-release.md`
- `backend/ai/docs/knowledge-ingestion.md`
- `backend/ai/docs/dataset-engineering.md`
- `backend/ai/docs/knowledge-data-governance.md`

## Verification

Chạy focused knowledge/dataset tests rồi `npm run verify:ai`. Dataset rights,
PII, ACL hoặc release luôn là controlled change.
