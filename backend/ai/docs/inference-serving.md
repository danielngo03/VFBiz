---
id: ai-inference-serving
title: Model Mesh và local inference serving
status: active
owner_role: engineering-lead
scope: ai
when_to_read:
  - local-inference
  - model-routing
  - provider-fallback
  - ai-finops
tags:
  - inference
  - vllm
  - finops
  - resilience
revision: 6
review_date: 2026-08-23
supersedes: []
---

# Model Mesh và local inference serving

## Routing contract

Model Router nhận capability, risk class, language, latency deadline, privacy
constraint và remaining budget; không nhận business authority. Tier là deployment
policy được version hóa, không hardcode một model name:

- T0: deterministic/classifier khi không cần generation.
- T1: approved local SLM/LLM.
- T2: low-latency cloud model.
- T3: high-capability cloud model.

Không bắt buộc mọi request đi tuần tự qua mọi tier. Router chọn tier thấp nhất
đạt acceptance; escalation/fallback có reason code và budget.

Application library hiện thực hóa contract này bằng `ModelMesh`,
`GenerationRequest` và `GenerationResult`; application lifespan chưa compose
library thành turn execution runtime cho tới khi VFBIZ-0114/0115/0094 đạt.
Một deployment chỉ được chọn khi toàn bộ immutable policy
descriptor khớp chính xác: policy revision, profile, safety tier, residency,
retention mode, structured-schema revision và model release. Mesh chỉ thử
deployment kế tiếp với lỗi transient có `retryable=true`;
lỗi authentication, invalid response, policy, budget hoặc cancellation dừng
ngay. Không có deployment tương đương trả `NO_SAFE_DEPLOYMENT`.

Circuit state được bảo vệ theo deployment; khi recovery chỉ đúng một half-open
probe được phép chạy. Mỗi adapter có bulkhead semaphore riêng và shared HTTP
client được đóng bởi application lifespan. Request pin `correlation_id`,
deadline, max attempts, input/output token và aggregate cost budget. Mỗi fallback
attempt giữ trước worst-case cost; không đủ budget thì dừng trước network call.
Kết quả giữ immutable attempt ledger gồm deployment, disposition, reserved và
incurred cost cùng normalized usage. Final usage/cost là tổng của mọi attempt,
không chỉ attempt thành công cuối cùng. Exception ngoài taxonomy được normalize
và luôn release half-open probe.

## OpenAI Responses adapter

OpenAI adapter là candidate production-capable provider đầu tiên, nằm trong
infrastructure và không đi vào domain/application policy. Nó chưa phải release
được phép dùng cho staging cho tới khi Assistant Release Manifest và grounding
assurance đạt. Contract HTTP được pin theo Responses
API chính thức ([OpenAI Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)):

- `POST /v1/responses`, không follow redirect;
- `store=false` để không lưu Response object cho product features; trường này
  **không đồng nghĩa** Zero Data Retention;
- `text.format.type=json_schema` và `strict=true`;
- `max_output_tokens` là min của request budget và deployment budget;
- `truncation=disabled`, không để provider tự bỏ evidence;
- `safety_identifier` chỉ được gửi khi upstream cung cấp SHA-256 hex digest,
  không gửi subject/email/phone thô;
- không yêu cầu hoặc parse reasoning/chain-of-thought;
- chỉ chấp nhận một `output_text` hoàn tất và citation ID thuộc evidence đầu vào;
- usage input/output/cached/reasoning được map sang typed telemetry, không lưu
  raw provider response.

Response body được đọc streaming với byte ceiling; answer, số citation, chiều
dài citation và evidence đều có local hard limit độc lập với provider usage.
Body `model` phải khớp exact approved snapshot/allowlist. Runtime trả một trong
`answered`, `insufficient_evidence`, `refused`; chỉ `answered` bắt buộc citation.
Citation membership chưa chứng minh claim được support: Model Mesh bắt buộc gọi
`ClaimSupportValidator`. Default runtime validator là fail-closed cho tới khi
validator deterministic/NLI có release evidence riêng.

Dynamic input được serialize thành canonical JSON versioned. Question, title,
source URI/revision, freshness và excerpt đều thuộc input digest; evidence được
coi là untrusted quoted data, không phải instruction. Digest thay đổi nếu bất kỳ
trường nào thực sự gửi tới model thay đổi.

Timeout, caller cancellation và HTTP transport cancellation được truyền tới
request đang chạy. `401/403`, `429`, `5xx`, timeout và invalid schema được map
thành failure code ổn định; provider message không được đưa vào exception/log
customer-facing. Tests dùng fake HTTP transport, không cần API key thật.

`disabled` vẫn là mặc định và tạo mesh rỗng fail-closed. `azure_openai` và
`self_hosted` còn nằm trong schema tương lai nhưng runtime cố ý từ chối vì chưa
có approved adapter; không được giả làm OpenAI-compatible rồi bỏ qua evaluation.

## Embedding runtime và quyền chọn provider

Embedding, generation và fine-tuning là ba lifecycle độc lập:

- embedding biến query/document thành vector để retrieval, không dạy chatbot
  văn phong hay cập nhật factual knowledge;
- generation tạo câu trả lời từ evidence đã được cấp;
- fine-tuning chỉ được mở cho kỹ năng ổn định sau khi evaluation chứng minh
  prompt, retrieval và deterministic tool chưa đủ.

Không provider nào là mặc định production. Runtime có một
`EmbeddingProvider` contract chung với hai candidate adapter:

- managed OpenAI Embeddings, bắt buộc project binding, model allowlist, approval
  evidence và release-manifest evidence;
- self-hosted Text Embeddings Inference (TEI)-compatible endpoint, chỉ cho phép
  HTTP trên loopback local/test và HTTPS ở môi trường khác.

Mỗi request pin purpose (`retrieval_query` hoặc `retrieval_document`) và
`EmbeddingGenerationIdentity`: model, tokenizer, weights, dimension, pooling,
normalization, input-template revision cùng SHA-256 của query/document template.
Identity có canonical digest và phải trùng tuyệt đối giữa active index, query
runtime và result. Request còn pin deadline, correlation ID và
item/byte/token/cost budget. Response phải giữ đúng count/order/index, finite vector và dimension;
không pad, truncate hoặc reorder im lặng. Managed usage là authority cho ledger
sau request; self-host candidate dùng token estimate bảo thủ cho tới khi serving
profile phát hành usage contract đáng tin cậy.

Query/document đi qua cùng một `EmbeddingRuntime` và cùng release-pinned
provider. Input template revision cùng query/document prefix là immutable
deployment policy; không dùng mutable template mặc định của inference server.
Cost ledger tách reservation trước network khỏi incurred cost do provider báo.
Self-hosted incurred cost để `unknown` cho tới khi serving profile cung cấp
resource-unit telemetry đáng tin cậy, không giả token estimate là hóa đơn thật.

Generation và embedding có riêng provider/model selection, pricing, concurrency
bulkhead, deadline, HTTP client/circuit state, release evidence và rollback.
Biến môi trường chỉ compose candidate đã được manifest cho phép; nó không tự
biến candidate thành release.

Việc đổi embedding model/dimension tạo một `EmbeddingIndexGeneration` mới,
materialize candidate index riêng, evaluate rồi atomic activate. Không ghi đè
vector đang active và không trộn query vector từ generation này với chunk của
generation khác.

Provider selection phải dựa trên recall/nDCG/MRR, hard-negative performance,
tiếng Việt có dấu/không dấu, latency p95/p99, cost, residency, operational burden
và failure isolation. Public leaderboard không đủ làm bằng chứng. OpenAI là
managed candidate giúp ra staging nhanh; TEI self-host là candidate kiểm soát
dữ liệu/chi phí ở quy mô lớn. Quyết định cuối có thể là managed-first,
self-hosted-primary hoặc hybrid, nhưng chỉ sau bake-off pin dataset và evaluator
revision.

Adapter enforcement:

- cancellation/deadline bao phủ cả thời gian chờ bulkhead và network stream;
  outer task cancellation phải hủy/await request đang chạy;
- response được đọc streaming với byte ceiling và output-element ceiling trước
  JSON/vector allocation lớn;
- rate limit thuộc admission/quota, không được làm “độc” provider-health circuit;
  transport timeout/unavailable và invalid response mới tác động health circuit;
- mỗi adapter sở hữu circuit/bulkhead riêng và chỉ đóng HTTP client do chính nó
  tạo;
- TEI candidate xác minh `/info` fingerprint gồm model, tokenizer, weights,
  input-template và deployment digest trước lần embed đầu tiên. Đây là contract
  của VFBiz attestation wrapper/sidecar, không phải contract mặc định được giả
  định từ stock TEI. Mỗi response `/embed` còn phải mang
  `x-vfbiz-embedding-deployment-sha256`; mixed replica hoặc deployment drift bị
  fail-closed;
- local/test chỉ cho loopback HTTP; staging/production cần HTTPS cùng workload
  service credential. Release review vẫn phải xác minh mTLS/service identity,
  egress allowlist và residency ở deployment layer.

## Retention và data controls

`store=false`, ZDR và Modified Abuse Monitoring là ba khái niệm khác nhau.
Deployment descriptor phải ghi retention policy thực tế của OpenAI project.
Candidate adapter yêu cầu project ID, organization binding, approval reference,
SHA-256 của approval artifact và SHA-256 của model release manifest; không chấp
nhận boolean “approved” tự khai báo. Các giá trị này mới là typed candidate
inputs, chưa phải durable authority. VFBIZ-0104 phải resolve artifact, tính lại
digest, kiểm trạng thái/effective window và human approval trước khi staging
runtime được bật. Adapter gửi project/organization header đã pin; policy
descriptor và generation result mang cùng evidence để Model Mesh kiểm tra exact
match. Security/Privacy vẫn phải kiểm tra cấu hình project, data residency và
hợp đồng; code không tự tuyên bố ZDR.

## Local serving baseline

Production-like local model dùng vLLM baseline. TensorRT-LLM chỉ là optional
profile khi phần cứng, quantization và benchmark chứng minh lợi ích. Development
server Python không được dùng làm production inference endpoint.

Capacity qualification gồm:

- model/quantization/tokenizer hash;
- PagedAttention/KV-cache utilization và prefix-cache isolation;
- continuous batching, scheduling fairness và per-profile quota;
- concurrency, input/output length distribution và time-to-first-token;
- OOM, worker restart, rolling upgrade và degraded mode;
- data remanence/cross-tenant leakage tests.

Không tuyên bố “hàng vạn request/GPU” nếu không có workload benchmark.

## Prompt caching

Static constitution/policy/stable few-shot đặt trước; profile/evidence/user state
đặt sau. Cache key pin prompt/policy/model revision và data class. Chỉ dùng cache
theo điều khoản/retention của provider. PII không được nhân bản vào prefix hoặc
log vì mục tiêu cache hit.

## Provider fallback

Circuit breaker dùng timeout/error-rate window và half-open probe. Fallback chỉ
sang deployment có capability, residency, privacy và safety profile tương đương.
Provider adaptation phải map tool/schema/finish reason nhất quán. Nếu không còn
safe deployment, trả Static Handoff; không hạ xuống model không đạt hard gate.

## Budget

Theo dõi input/output/cached token, tool cost, latency và retry theo request,
session, subject/tenant và release. Router chặn amplification, context stuffing
và retry loop. Cost optimization không được làm giảm ACL, citation hoặc safety
gate.

Preflight dùng ước lượng token bảo thủ để chặn payload rõ ràng vượt ngân sách;
usage do provider trả về vẫn là authority cho ledger sau request. Việc token
thực tế vượt budget làm response fail-closed, không được release câu trả lời.
Prompt/model/policy revisions là immutable input của release manifest.

## Kiểm thử

- Same-tier provider timeout/5xx fallback và all-provider failure.
- Model mismatch, oversized body, local output limit và 20 concurrent half-open
  request chỉ tạo một probe.
- Unrelated evidence không qua claim-support gate; insufficient evidence trả
  typed outcome không cần citation.
- Prompt-cache hit/miss không đổi output policy hoặc data isolation.
- Session/tenant budget exhaustion và unsafe downgrade refusal.
- KV-cache pressure, cancellation, OOM recovery và rolling update.
