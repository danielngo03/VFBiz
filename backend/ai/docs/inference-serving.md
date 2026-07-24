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
revision: 1
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

## Kiểm thử

- Same-tier provider timeout/5xx fallback và all-provider failure.
- Prompt-cache hit/miss không đổi output policy hoặc data isolation.
- Session/tenant budget exhaustion và unsafe downgrade refusal.
- KV-cache pressure, cancellation, OOM recovery và rolling update.
