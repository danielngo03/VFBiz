# Build, update và release

## Environments

Development, preview và production có bundle/package identifier, OIDC client,
API URL, EAS channel và data partition riêng. Preview không tự động đồng nghĩa
VFBiz staging cho tới Release Owner chốt mapping.

EAS command chạy từ `mobile/customer`. Development profile tạo dev client;
preview internal; production store distribution + auto-increment. Signing keys,
store API keys và source-map token chỉ ở approved secret store.

OTA đang disabled. Chỉ bật sau runtime fingerprint compatibility, code signing,
channel isolation, internal -> 5% -> 25% -> 100% rollout, kill/cancel/rollback
rehearsal và incident owner. Native dependency/permission/entitlement/privacy
manifest change phải tạo store build mới.

Release evidence: immutable Git revision, lockfile, Expo Doctor, unit/contract/
accessibility/Maestro results, iOS/Android artifact digest, dependency/SBOM scan,
privacy/security review, store metadata/asset rights và rollback proof.

Agent không submit store hoặc rollout production. Architect, Security Owner,
Privacy Owner và Release Owner gates vẫn mở sau code-complete.

Preview/production bị khóa nếu chưa có exact native callback registration,
signed-manifest permission evidence, backup/restore evidence và dependency-risk
record được Security, Privacy, Identity và Release owners xử lý.

## Gate handoff

Engineering Lead tập hợp revision, lockfile, build/test/security evidence.
Reviewer-verifier độc lập kiểm acceptance/regression; risk-reviewer trả finding
cho auth, PII, dependency và release nhưng không chấp nhận risk. Product,
Architect, Security, Privacy và Release Owners ghi decision vào VFBIZ-0203/ADR.

Release Owner là người duy nhất tiến rollout. Sự cố sau handoff thực thi theo
`runbook.md`; không nhân bản runbook vào checklist hoặc agent message.
