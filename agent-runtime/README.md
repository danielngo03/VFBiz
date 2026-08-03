# VFBiz Enterprise Agent Runtime

`@vfbiz/agent-runtime` là control plane chạy cục bộ trên một máy, dùng để điều
phối công việc của coding agent theo governance của VFBiz. Runtime giải quyết
context và quyền trước khi gọi model, duy trì hàng đợi có thể phục hồi sau khi
khởi động lại, lưu ledger trong SQLite và chỉ trao đổi giữa các specialist bằng
kiểu dữ liệu đã xác định.

Đây **không phải** Customer Chatbot, AI Platform phục vụ khách hàng hoặc một hệ
thống có quyền tự release. Tắt Agent Runtime không ảnh hưởng tới quy trình Git,
work item và các lệnh phát triển hiện có.

## Khi nào nên dùng

Không cần khởi động runtime cho phiên Codex tương tác thông thường. Mở Codex tại
repository root hoặc workspace sở hữu công việc:

```bash
cd /path/to/VFBiz
codex

codex -C backend/api
codex -C backend/ai
codex -C agent-runtime
```

Chỉ dùng Agent Runtime khi công việc cần một hoặc nhiều khả năng sau:

- hàng đợi bền vững, có thể tiếp tục sau khi tiến trình bị dừng;
- điều phối specialist bằng input/output có schema;
- checkpoint mã hóa và phục hồi approval interruption;
- ngân sách theo turn/token và ledger sử dụng;
- bằng chứng vận hành để bàn giao giữa worker và Codex Desktop.

## Ranh giới an toàn

- Git work item, claim, fencing token và context resolver là authority; model
  không được tự hạ mức governance.
- Runtime v1 không cung cấp public endpoint, không truy cập product database và
  không có quyền merge, deploy, release hoặc chấp nhận rủi ro.
- Codex coding executor chỉ được ghi vào repository fixture đã đăng ký dưới
  `tests/fixtures`; product workspace luôn read-only đối với runtime v1.
- Reviewer chỉ đưa finding; agent không tự phê duyệt Product, Security, Legal,
  Data/Privacy hoặc Release.
- Secret, checkpoint rõ, objective thô và payload approval không được ghi vào
  Git hoặc in ra resume brief.

## Kiến trúc

```text
CLI / Worker
    │
    ├── Governance Gateway ── context, claim, fencing, allowed paths
    ├── Application Use Cases ── enqueue, execute, resume, cancel, reconcile
    ├── Agents SDK Executor ── orchestrator và typed specialists
    ├── Codex Fixture Executor ── isolated temporary worktree
    └── SQLite Ledger ── run, event, approval, usage, encrypted checkpoint
```

OpenAI Agents SDK là orchestration SDK hiện tại. Model provider nằm sau
`OpenAIProvider`, vì vậy runtime hỗ trợ cả OpenAI và endpoint triển khai giao
thức OpenAI-compatible. Việc đổi endpoint không làm thay đổi governance,
approval, persistence hoặc tool boundary.

## Cấu hình model provider

Live provider mặc định tắt. Không ghi key vào repository hoặc commit file
`.env`. File [`.env.example`](.env.example) là authority cho danh sách biến,
giá trị mặc định an toàn và tên model override theo role:

```bash
cp agent-runtime/.env.example agent-runtime/.env
# Điền key, model, cost rate và state key trong agent-runtime/.env.
set -a
source agent-runtime/.env
set +a
npm run agent-runtime:doctor
```

OpenAI dùng `VFBIZ_AGENT_RUNTIME_PROVIDER=openai` và Responses API theo mặc
định. Provider/gateway tương thích OpenAI dùng
`VFBIZ_AGENT_RUNTIME_PROVIDER=openai-compatible`, một base URL riêng và mặc
định Chat Completions. `VFBIZ_AGENT_RUNTIME_API_KEY` là key thống nhất;
`OPENAI_API_KEY` chỉ còn là fallback để tương thích cấu hình cũ.

Endpoint từ xa bắt buộc HTTPS. HTTP chỉ được chấp nhận với loopback
`localhost`, `127.0.0.1` hoặc `::1` cho gateway/model server local. URL không
được chứa credential, query hoặc fragment.

Key native của Anthropic, Gemini hoặc provider khác **không tự động tương
thích**. Provider/gateway phải triển khai đúng API mode, model ID, streaming,
structured output và tool calling mà workflow sử dụng. Nếu chỉ có native API,
cần một adapter riêng thay vì đổi tên biến key. Luôn chạy `doctor`, unit/eval và
một fixture canary trước khi cho worker xử lý công việc.

Tracing của Agents SDK là một kênh riêng. Giữ
`VFBIZ_AGENT_RUNTIME_TRACE_ENABLED=false` với provider compatible trừ khi đã xác
minh rõ nơi nhận trace, retention và chính sách dữ liệu.

State mặc định nằm dưới Git common directory, dùng quyền thư mục `0700` và
database `0600`. Nhờ vậy các worktree trên cùng máy dùng chung ledger mà không
đưa state vào working tree.

## Lệnh vận hành

```bash
# Thêm một run đã có work item/claim hợp lệ
npm run agent-runtime -- enqueue \
  --work VFBIZ-0204 \
  --claim <claim-id> \
  --fencing-token <token>

# Xử lý một job hoặc chạy worker liên tục
npm run agent-runtime -- worker --once
npm run agent-runtime -- worker --watch

# Xem trạng thái và approval
npm run agent-runtime -- status --run <run-id>
npm run agent-runtime -- approvals list

# Tạo context bàn giao an toàn
npm run agent-runtime:brief -- --work VFBIZ-0204 --target agent-runtime

# Chẩn đoán và chạy evaluation fixtures
npm run agent-runtime:doctor
npm run agent-runtime:eval
```

Controlled work không thể enqueue nếu thiếu claim và fencing token canonical.
Runtime kiểm tra lại context revision, claim và allowed paths trước dispatch và
sau provider call; provider hoàn thành không đồng nghĩa công việc được chấp
nhận.

## Bàn giao và phục hồi

Runtime và Codex Desktop không chia sẻ conversation memory của provider. Trước
khi để worker chạy không giám sát, cập nhật checkpoint của work item với revision,
file đã đổi, kiểm tra đã quan sát, blocker và đúng một next action.

Lệnh `agent-runtime:brief` kết hợp Git truth với SQLite state, nhưng không giải
mã checkpoint hoặc trả raw event payload. Context cũ, heartbeat hết hạn,
approval đang chờ hoặc operation không chắc chắn đều là stop condition; runtime
không tự suy diễn quyền tiếp tục.

## Kiểm tra chất lượng

```bash
npm run verify:agent-runtime
npm run governance:check
```

Live provider không nằm trong test mặc định. Test mặc định dùng deterministic
fixtures; live canary phải được bật rõ ràng, có cost policy và không được dùng
dữ liệu sản phẩm hoặc secret làm fixture.

Tài liệu chi tiết:

- [Kiến trúc](docs/architecture.md)
- [Vận hành và phục hồi](docs/operations.md)
- [Evaluation](docs/evaluation.md)
