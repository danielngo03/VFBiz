---
report_id: VFBIZ-WEEK-02
title: Báo cáo tuần 2 — Customer Chatbot và AI Assurance
period_start: 2026-07-27
period_end: 2026-08-01
audience: mentor
owner_role: product-owner
status: ready-to-send
evidence_cutoff: 731ba5f459eada0ac9af52b179c74f8e6696d40d
---

# Báo cáo tuần 2 — Customer Chatbot và AI Assurance

**Thời gian:** 27/07/2026 – 01/08/2026

**Mục tiêu tuần:** Xây dựng nền tảng Customer Chatbot có trạng thái bền vững,
nguồn tri thức được quản trị và cơ chế đánh giá có bằng chứng; đồng thời giữ
Chat public ở trạng thái đóng cho đến khi đủ dữ liệu và thẩm quyền phát hành.

## 1. Tóm tắt kết quả

Trong tuần 2, dự án chuyển từ kiến trúc và contract nền tảng sang các thành phần
runtime có thể kiểm thử độc lập:

- Hoàn thiện nền Conversation Runtime giữa API Platform và AI Platform: session,
  turn, message, replay SSE, cancellation, handoff, OCC, fencing và transport nội
  bộ có chữ ký.
- Xây dựng AI runtime theo hướng provider-neutral, gồm state machine hội thoại,
  retrieval, citation/refusal, model policy, budget và release-bound execution.
- Xây dựng Knowledge Release control plane với ingestion, materialization,
  retrieval snapshot, active release pointer, revocation fence và atomic
  activation.
- Hoàn thiện Dataset Registry foundation, contract Dataset Manifest v4 và các
  gate provenance/release để candidate không tự trở thành dữ liệu được phát
  hành.
- Bổ sung Evaluation control plane và `EvidenceBundleAuthority`; digest được
  tính lại từ case result bất biến thay vì chấp nhận một digest tùy ý.
- Bổ sung semantic routing có binding theo release và task-slot authority để
  duy trì ngữ cảnh qua clarification, correction và chuyển chủ đề.
- Chuẩn hóa reviewer cho dataset/Golden, dependency risk snapshot, maturity
  matrix và các gate governance dùng chung.

Kết quả trên là **code/evidence foundation**, chưa phải bản Chatbot public hoặc
production release.

## 2. Kết quả theo nhóm công việc

### 2.1. Conversation Runtime và API–AI trust

- API Platform giữ durable conversation state, sequence, retry, cancellation,
  handoff và final response.
- Event stream hỗ trợ replay theo cursor; disconnect không được coi là kết thúc
  phiên hội thoại.
- Giao tiếp API–AI dùng execution assertion có thời hạn, kiểm audience, subject,
  release revision và response authenticity.
- Task context và task-slot receipt được lưu bền vững; opaque value không bị
  đưa vào phần context mà model có thể đọc tùy ý.
- Authorization boundary được củng cố theo nguyên tắc API giữ business
  authority, AI chỉ trả về typed outcome/tool proposal.

### 2.2. AI orchestration, routing và grounded answer

- Conversation graph được hợp nhất quanh state, cancellation, budget và
  checkpoint có revision.
- `KnowledgeGroundedWorker` thực hiện retrieval trước generation và kiểm citation
  trước khi trả lời factual.
- Semantic classifier binding được quản trị theo release; contract output được
  pin và persistence lifecycle được bổ sung.
- Deterministic safety/injection rule vẫn đứng trước semantic routing; khi
  evidence không đủ, luồng phải clarification, refusal hoặc handoff.
- Runtime vẫn fail closed nếu chưa resolve được release/provider/policy phù hợp.

### 2.3. Knowledge và Dataset governance

- Knowledge ingestion có state machine, idempotency, fencing, replay control và
  content-addressed artifact.
- Candidate materialization và retrieval snapshot được tách khỏi active release;
  activation dùng pointer nguyên tử và có khả năng revoke/rollback.
- Dataset Registry lưu source, fetch và artifact metadata; payload lớn không
  được đưa vào PostgreSQL hoặc Git.
- Dataset Manifest v4 trở thành contract runtime; v3 chỉ còn vai trò import
  legacy. Release provenance và maker-checker boundary được kiểm tra riêng.
- Dataset/Golden reviewer được tách vai trò để builder không tự duyệt dữ liệu do
  chính mình tạo.

### 2.4. Evaluation và evidence authority

- Evaluation plan, case execution, durable sharding, retry, cancellation và
  budget accounting đã có persistence.
- `EvaluationRun.complete(arbitrary_digest)` được loại bỏ.
- Khi seal, hệ thống tính lại canonical digest từ immutable latest-attempt case
  results và kiểm exact suite completeness, grader revision, calibration,
  baseline policy cùng hard gates.
- Migration `20260730_0020` yêu cầu evidence row khớp trước khi run chuyển sang
  `decision_ready`; direct update, stale lease và evidence tampering bị từ chối.
- Automated evidence chỉ đưa ra `needs-human-decision`; evaluator không có quyền
  tự phát hành model, dataset hoặc Chatbot.

## 3. Công việc theo ngày

| Ngày        | Trọng tâm                                | Kết quả có checkpoint trong repository                                                                                                                                                   |
| ----------- | ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 27/07       | Củng cố nền tảng delivery, API và Chat   | Chuẩn hóa agent governance/security CI; hợp nhất authorization boundary, durable Conversation Runtime, provider-neutral AI runtime, Knowledge Release và trusted conversation contracts. |
| 28/07       | Dataset, evaluation và trust boundary    | Cứng hóa API–AI trust, Dataset Registry intake, evaluation control plane, source catalog, dataset/Golden review board và tài liệu kiến trúc.                                             |
| 29/07       | Continuity, routing và release authority | Bổ sung durable task context/slot authority, semantic classifier binding, Dataset Manifest v4/release provenance và capability maturity truth.                                           |
| 30/07       | Runtime composition và evidence sealing  | Nối governed semantic routing; hoàn thiện evidence bundle authority, migration 0020 và ghi rõ các human gate cho Dataset/Chat staging.                                                   |
| 31/07–01/08 | Không có checkpoint mới                  | Không suy diễn thêm kết quả ngoài bằng chứng đã ghi trong repository; khoảng thời gian này được dùng làm điểm kết thúc báo cáo.                                                          |

Trong kỳ có **27 checkpoint** được ghi nhận. Con số này dùng để truy vết phạm vi
thay đổi, không được dùng thay cho tiêu chí chất lượng hoặc release.

## 4. Bằng chứng kiểm tra chất lượng

Các con số dưới đây là snapshot theo từng work item tại thời điểm chạy; chúng
chồng lấp nhau nên không được cộng thành một tổng test duy nhất.

| Work item    | Bằng chứng đã ghi nhận trong kỳ                                                                                                                                                                                          |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `VFBIZ-0192` | Contract lint qua 34 AI contracts/55 vectors; Python–Node canonical digest parity; 561 AI tests; PostgreSQL 17 + pgvector integration; tamper/direct-ready/budget tests; governance check. Trạng thái cuối kỳ: `review`. |
| `VFBIZ-0191` | API lint/typecheck, 377 unit tests, 67 E2E tests, 42 PostgreSQL integration cases; 536 AI tests; contract và governance gates. Independent reviewer không còn P0/P1/P2.                                                  |
| `VFBIZ-0169` | 550 AI tests, full PostgreSQL integration và 34 contracts/55 vectors cho semantic routing. Activation vẫn phụ thuộc evaluation evidence.                                                                                 |
| `VFBIZ-0134` | 393 AI tests, Dataset contract vectors và governance check cho Source/Fetch/Artifact foundation.                                                                                                                         |

Ngoài test tự động, kỳ này bổ sung các negative gate cho stale revision,
incomplete suite, direct `decision_ready`, update/truncate evidence, invalid
task context và unauthorized release transition.

## 5. So sánh với MVP tuần 2 đã đề ra

### Đã tiến triển đúng hướng

- Conversation Runtime và private API–AI protocol đã có implementation và test.
- Knowledge/Dataset/Evaluation foundation đã có persistence, contract và
  fail-closed gate.
- Chatbot đã có nền citation, refusal, handoff và durable task continuity.
- Governance cho agent, dataset và release được làm rõ hơn; builder không tự
  đóng vai reviewer/release owner.

### Chưa hoàn thành trong kỳ

- Chưa có browser E2E hoàn chỉnh cho login → Chat → reconnect/cancel → logout.
- Chưa có first-party VinFast Knowledge Release được Content/Legal/Data owner
  chấp nhận.
- Chưa có Golden Release 1.000 case được con người adjudicate.
- Chưa có authenticated staging hoặc public Chat activation.
- Chưa có bằng chứng Vertex product-runtime, cloud ingestion end-to-end hoặc
  fine-tuning. Fine-tuning vốn nằm ngoài MVP tuần 2 và không được dùng để thay
  thế factual knowledge/citation.
- Customer/Workforce Portal vẫn cần hoàn tất các hành trình E2E đã nêu từ tuần 1.

## 6. Rủi ro và quyết định giữ an toàn

- Không coi test pass là production release.
- Không dùng dữ liệu VinFast chưa có quyền/provenance làm Golden hoặc training.
- Không để AI tự tạo giá, chính sách, thông số xe hoặc business mutation.
- Không mở public Chat khi source revision, evaluation, security và rollback
  evidence chưa đầy đủ.
- Không để model judge, coding agent hoặc dataset builder giả Product/Brand/
  Legal/Data/Release approval.

## 7. Ưu tiên tuần tiếp theo

1. Hoàn tất independent acceptance cho `VFBIZ-0192` và khóa canonical evidence
   parity trên PostgreSQL.
2. Nối provider runtime và cloud ingestion theo release manifest, cost ledger
   và kill switch; bắt đầu bằng synthetic/pilot data có giới hạn.
3. Hoàn thiện governed source register, Dataset Release và Golden candidate;
   tách tuyệt đối knowledge, training, Golden và red-team data products.
4. Chạy baseline evaluation trước khi quyết định có fine-tuning hay seal
   `no-submit`.
5. Hoàn thiện API/Portal authenticated staging E2E; tiếp tục từ chối anonymous
   Chat cho đến khi đủ release authority.

## 8. Nguồn kiểm chứng

- Phạm vi thời gian được đối chiếu từ các checkpoint ngày 27–30/07/2026; cutoff
  của báo cáo là revision `731ba5f459eada0ac9af52b179c74f8e6696d40d`.
- Evidence chi tiết: `docs/work/items/VFBIZ-0134.md`, `VFBIZ-0167.md`,
  `VFBIZ-0169.md`, `VFBIZ-0191.md` và `VFBIZ-0192.md` tại cutoff trên.
- Kiến trúc đích tham chiếu bộ `reports/common`; bộ này không được dùng để suy
  ra trạng thái triển khai.
