# Authority cho Customer Mobile release

Build thành công không đồng nghĩa release. Trạng thái tách biệt:
code-complete, acceptance-complete, released và outcome-validated.

Mobile Experience tạo reproducible artifact/evidence. Security và Privacy duyệt
auth, permission, telemetry, PII/offline. Product Owner duyệt scope/copy. Design
Lead duyệt experience/accessibility/brand use. Release Owner duyệt signing,
distribution, staged rollout, rollback và store submission.

OTA là production release surface của Customer và đang khóa. Chỉ bật sau signed
updates, runtime compatibility, environment/channel isolation, staged rollout,
kill/cancel/rollback rehearsal và incident runbook. Native dependency,
entitlement, permission hoặc privacy-manifest change cần store build mới.

Agent không giữ signing credential, không chấp nhận risk và không submit/rollout
production. Approval được ghi bằng Git evidence/CI artifact, không bằng lời nói
giữa agents.
