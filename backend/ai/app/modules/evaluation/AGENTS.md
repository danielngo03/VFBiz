# AI Assurance — Evaluation

## Ownership

- Sở hữu offline/security/regression evaluation suite, grounding/claim-support
  validation, red-team, shadow evidence và release-gate threshold check.
- Không tự activate/rollback release (Governance là authority); Evaluation
  chỉ sinh evidence, không tự phê duyệt hay promote.

## Invariants

- Automated gate sinh evidence, không phải approval; Release Owner là
  authority duy nhất chấp nhận evidence để promote.
- Claim-support validator dùng ensemble (citation membership, numeric/entity/
  temporal rule, contradiction detector, approved NLI/judge signal) — một
  lexical/exact-match signal đơn lẻ không đủ chứng minh entailment.
- Validator pin model/rules/threshold/calibration-dataset/evaluator revision;
  có budget, timeout, cancellation và fail-closed behavior.
- Evaluation và training split tách biệt; không đưa held-out failure ngược
  vào tuning trước khi tạo suite revision mới.
- Poisoned evidence, cross-revision, partial support, conflicting source hoặc
  judge outage đều không được phát hành factual answer.

## Read when applicable

- `backend/ai/docs/evaluation-and-release.md`
- `backend/ai/docs/safety-and-abuse.md`

## Verification

Chạy focused evaluation/security tests rồi `npm run verify:ai`. Thay đổi
threshold, validator revision hoặc release-gate logic luôn là controlled
change cần Release Owner.
