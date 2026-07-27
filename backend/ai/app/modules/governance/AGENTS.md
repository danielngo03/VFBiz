# AI Assurance — Release Governance

## Ownership

- Sở hữu release manifest/candidate, approval, activation, rollback,
  revocation và audit trail cho Assistant Release.
- Không tự chọn model/provider (Model Platform), không tự quyết retrieval
  content (Knowledge Engineering), không tự sinh evaluation evidence
  (Evaluation sinh evidence; Governance chỉ tiêu thụ và ký nó vào manifest).

## Invariants

- Fail closed khi activation stale, revoked, cross-profile hoặc digest
  mismatch trước khi runtime provider được gọi.
- Rollback target phải từng là candidate active/superseded hợp lệ trong cùng
  profile/environment; không tự tham chiếu hoặc tạo cycle.
- Một release gate không tự promote candidate của chính nó; Release Owner là
  authority duy nhất cho promotion/rollback.
- Activation dùng optimistic concurrency và append-only audit; candidate
  artifact identity là immutable sau khi ký.
- Kill-switch phải là registry thật có khả năng chặn resolution trong cùng
  cửa sổ freshness đã áp cho stale pointer — không chỉ là evidence digest
  được xác thực là "tồn tại" (xem VFBIZ-0126).

## Read when applicable

- `backend/ai/docs/inference-serving.md`
- `backend/ai/docs/evaluation-and-release.md`
- `../../../../docs/governance/security-data-ai.md`

## Verification

Chạy focused governance tests với `VFBIZ_RUN_DB_INTEGRATION=1` cho integration
suite thật trên PostgreSQL, rồi `npm run verify:ai`. Release activation,
rollback hoặc kill-switch luôn là controlled change cần Release Owner.
