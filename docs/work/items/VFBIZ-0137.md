---
id: VFBIZ-0137
title: Fetch approved ViVi Wave A public datasets
status: active
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai
  - contracts/ai
  - docs/work/items/VFBIZ-0137.md
  - WORK.md
depends_on:
  - VFBIZ-0133
controlled_signals:
  - dataset-source
exclusive_resources:
  - ai-source-registry
required_checks:
  - npm run verify:ai
  - npm run contracts:lint
  - npm run governance:check
revision: 8
review_date: "2026-08-28"
updated_at: "2026-07-28T08:19:30Z"
---

# Outcome

Fetch từng source Wave A đã được Data Owner cho phép vào quarantine với exact
revision, observed hashes, structural scan và lineage. MIRACL/NoMIRACL không
được dùng cho Vietnamese vì upstream official không có Vietnamese.

## Constraints

- Không tải toàn bộ source lớn thiếu chọn lọc; không chạy remote dataset
  code/trust_remote_code.
- Fetch approval không đồng nghĩa purpose approval hoặc release.

## Done when

- Mỗi fetch pin exact upstream revision/origin, content hash, scan và deletion evidence.
- Evaluation/golden source không được xuất hiện trong training mixture.

## Checkpoint

- Data Owner đã cấp fetch approval trong task ngày 2026-07-28.
- Đã đối chiếu 18/18 hash và nhập vào content-addressed quarantine tại
  `local-data/ai-datasets/quarantine`; directory/file dùng quyền `0700/0600`.
- Portfolio hiện có payload cho đủ 11/11 source Wave A. xLAM gated terms đã
  được Data Owner chấp nhận; exact revision chứa 60.000 record và vẫn chỉ có
  quyền quarantine fetch.
- Aya Collection chỉ lấy hai Vietnamese train shards; UltraChat chỉ lấy ba
  `train_sft` shards; BFCL chỉ lấy 16 file evaluation bất hoạt.
- Bổ sung VieQuAD Retrieval, SeaBench, SafePyramid, IFEval và RAGTruth vào
  evaluation/red-team portfolio riêng; tuyệt đối không làm training seed.
- Bổ sung Vietnamese Function Calling Test 2.899 case vào restricted evaluation;
  hai email-shaped value giữ artifact trong quarantine chờ DLP adjudication.
- Bổ sung VMLU đủ bốn public release: Vi-MQA 1.5, Vi-SQuAD 1.0, Vi-DROP
  1.0 và Vi-Dialog 1.0. Bốn ZIP được kiểm hash, ClamAV và giải nén bằng
  extractor chống path traversal, symlink, encrypted entry và archive bomb.
- Bổ sung V-Bench public release `v2026.03.28`: 9.141 public test case và
  sample submission. Professional test tiếp tục human-blocked vì upstream yêu
  cầu liên hệ; không suy diễn rằng toàn bộ benchmark 40.000+ task là public.
- Tám artifact VMLU/V-Bench đã được đối chiếu exact hash và nhập vào
  content-addressed quarantine; incremental portfolio reconciliation không có
  missing source hoặc selector drift.
- Fetcher hiện ràng buộc exact revision, artifact selector, approval digest,
  expected size và upstream SHA-256.
- Full inspection đã đọc 57 artifact, 2.227.143.867 byte và 4.376.809 record;
  không có malformed artifact.
- ClamAV 1.5.3 với signature revision 28075 quét 57/57 payload file và bốn
  VMLU transport ZIP, không phát hiện malware. DLP giữ 25 artifact để review
  PII candidate và một HelpSteer2 artifact để review AWS-shaped secret candidate.
- Registry không còn cho phép fetch chuyển sang `scan-passed` nếu thiếu evidence,
  evidence không bind đúng content hash hoặc còn DLP/malware/structure blocker;
  scan evidence được round-trip qua PostgreSQL thay vì bị ghi thành object rỗng.
- Purpose/release vẫn human-blocked cho tới khi có Legal/Data approval và
  production malware/DLP evidence.

## Evidence

- [x] `npm run verify:ai` — 433 passed, 80 external-integration tests bị loại
      khỏi fast suite.
- [x] `npm run contracts:lint` — OpenAPI và 18 dataset contract vectors đạt.
- [x] Dataset Registry PostgreSQL integration — 2/2 test đạt, gồm OCC source
      và round-trip content-bound scan evidence.
- [ ] `npm run governance:check` — blocked by pre-existing stale `docs/INDEX.json`
  from concurrent documentation WIP.
- [x] Structural scan — 18/18 quarantine artifact valid; hashes recorded in
      `backend/ai/dataset-specs/sources/public/wave-a-smoke-fetch-evidence.json`.
- [x] Local reconciliation — `consolidated-checkpoint` ghi immutable content address,
      bytes, scan state và promotion blockers cho từng artifact.
- [x] Full Parquet/JSON/JSONL inspection — 4.376.809 record, không malformed.
- [x] Malware scan — 57 payload file và bốn VMLU ZIP, 0 infected; durable checkpoint tại
      `wave-a-security-evidence.json`.
- [ ] DLP adjudication — 25 PII-candidate artifact và một secret-candidate
      artifact tiếp tục bị quarantine.
- [ ] Purpose approval/independent release review — chưa được cấp.
