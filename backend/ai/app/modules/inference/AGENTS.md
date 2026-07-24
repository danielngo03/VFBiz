# AI Model Platform

## Ownership

- Sở hữu provider-neutral Model Mesh, model routing, local/cloud adapters,
  prompt-cache mechanics, cancellation và FinOps runtime.
- Không sở hữu dataset rights, retrieval content hoặc assistant business policy.

## Invariants

- Provider/model không tạo authority; fallback phải tương đương capability/risk.
- Production-like local serving dùng vLLM baseline hoặc profile đã benchmark.
- Không hạ tier nếu làm mất safety, ACL hoặc citation gate.
- Prompt cache pin revision/data class; không nhân bản PII để tăng cache hit.
- All-provider failure trả typed failure cho Static Handoff, không bịa response.

## Read when applicable

- `backend/ai/docs/inference-serving.md`
- `backend/ai/docs/architecture.md`

## Verification

Chạy focused inference/provider tests rồi `npm run verify:ai`. Deployment,
capacity, secret hoặc residency thay đổi cần SRE/Security authority.
