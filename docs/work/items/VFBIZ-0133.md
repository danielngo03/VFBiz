---
id: VFBIZ-0133
title: Canonical dataset governance contracts
status: done
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - contracts/ai
  - contracts/json-schema
  - backend/ai/dataset-specs
  - backend/ai/.agents/skills
  - backend/ai/tests
  - backend/ai/docs
  - tools/check-agent-governance.mjs
  - tools/check-runtime-contracts.mjs
  - tools/lib/governance.mjs
  - docs/work/items/VFBIZ-0133.md
  - WORK.md
depends_on: []
controlled_signals:
  - dataset-source
  - synthetic-dataset
  - dataset-release
  - schema
exclusive_resources:
  - dataset-registry
  - ai-dataset-contract
required_checks:
  - npm run contracts:lint
  - npm run governance:check
  - npm run verify:ai
revision: 10
review_date: "2026-08-28"
updated_at: "2026-07-28T03:45:16.271Z"
---

# Outcome

Dataset Factory dùng một bộ contract canonical cho Source Register, fetch
artifact, candidate, golden case, generation job và Dataset Release Manifest;
mọi download bị chặn trước network nếu chưa có human fetch approval nhưng
checksum quan sát được chỉ bắt buộc sau khi artifact vào quarantine.

## Constraints

- Không download public dataset hoặc tạo approval giả trong work item này.
- Không chạm migration/lockfile đang thuộc các lane Chatbot active.
- Source fetch approval và purpose approval là hai quyết định độc lập.
- Evaluation/red-team không được trở thành knowledge hoặc training candidate.
- Canonical JSON Schema là authority chung cho TypeScript, Python và database boundary.

## Done when

- Source Register v3 và Source Fetch Manifest mô tả lifecycle tách biệt, có positive/negative vectors.
- Runtime và governance chỉ dùng một Dataset Release Manifest canonical.
- Golden case v2 pin claim/citation/tool/state/adjudication và chỉ cho phép evaluation.
- Generation job pin coverage matrix, shard lease, budget và prohibited inputs.
- Hai dataset skill validate trực tiếp canonical schema, có metadata chính thức và realistic tests.
- Public source candidates chỉ là metadata; không artifact nào được tải hoặc release.

## Checkpoint

- VFBIZ-0130 và VFBIZ-0132 tiếp tục chờ review độc lập; dataset lane không sửa
  internal conversation contract, migration hoặc lockfile của hai work item đó.
- Canonical contracts, cross-language vectors, public candidate metadata,
  golden target/rubric, skill scripts và focused agent review profiles đã hoàn tất.
- Hardening sau review nội bộ đã tách đúng candidate/release storage zone, yêu
  cầu Data Owner + Release Owner khi release và thêm bounded exact-origin
  quarantine fetcher. Vì evidence hash đã đổi, vẫn cần independent review mới.
- Review cycle 1 phát hiện binding/checksum, false schema evidence,
  Golden-v2 contamination và cross-field manifest invariants; writer đã sửa và
  bổ sung adversarial vectors. Review cycle 2 xác nhận các nhóm này đã đóng,
  sau đó tìm DNS TOCTOU và citation-snapshot membership; cả hai đã được sửa bằng
  pinned-IP HTTPS transport và semantic validation parity. Không mở review vòng
  ba nếu không có evidence mới theo anti-loop policy.
- Exact next action: checkpoint riêng các file VFBIZ-0133 rồi ghi lại controlled
  implementer/reviewer/risk runs bằng Agent Control. Work-control đã fail-closed
  khi thử chuyển `done` vì session trước không có implementation ledger; không
  mở VFBIZ-0134 hoặc giả mạo ledger trong dirty mixed worktree.

## Evidence

- [x] `npm run contracts:lint` — 5 OpenAPI, 6 runtime schema, 12 shared
      dataset contract vectors và 24 workforce capabilities đạt ngày 2026-07-28.
- [x] `npm run governance:check` — docs/reports/work/skills và 72 context
      scenarios đạt ngày 2026-07-28.
- [x] `npm run verify:ai` — Ruff, Pyright, 388 tests và Alembic SQL đạt ngày
      2026-07-28; 78 external-database tests thuộc fast-suite exclusion.
- [x] `VFBIZ_RUN_DB_INTEGRATION=1 npm run verify:ai:integration` — toàn bộ
      PostgreSQL 17.10/pgvector integration suite đạt trên port local 5434,
      không dùng skip làm acceptance.
- [x] Official `quick_validate.py` — cả `onboard-dataset` và
      `generate-synthetic-dataset` hợp lệ; `agents/openai.yaml` được sinh bằng
      official generator với trigger-rich prompt.
- [x] Independent review cycle 1/2 — 7 finding được tái hiện và đóng bằng
      adversarial tests; vòng ba bị chặn theo anti-loop policy khi không có
      evidence mới.

### ready — 2026-07-27T18:12:19.165Z

Scope and human gates are explicit.

### active — 2026-07-27T18:12:19.307Z

Implementing canonical contracts without dataset download.

### review — 2026-07-27T18:27:53.608Z

Implementation and deterministic evidence complete; independent review and human rights/data authority remain required.

### done — 2026-07-28T03:45:16.271Z

Checkpointed canonical dataset contracts in consolidated-checkpoint and governance scope alignment in consolidated-checkpoint; independent contract, governance, AI and PostgreSQL integration verification passed.
