# Generation contract

The job validates against `contracts/ai/generation-job.schema.json` and pins:

- dataset/purpose/profile/schema revision;
- approved seed/source references or synthetic fact namespaces;
- generator model, prompt, policy, temperature and deterministic seed;
- max records, input/output tokens and cost;
- intent/risk/locale/failure-mode coverage;
- unique shard ID, output prefix and lease;
- prohibited inputs including production PII and held-out evaluation.

One builder owns one shard. Shard contents are candidate-only and live in
approved object storage or a temporary gitignored path. Registry and release
manifest are single-writer resources controlled by the orchestrator/Data Owner.

Generation should vary diacritics, typo, slang, code-switch and multi-turn while
preserving the expected policy outcome. It must not invent real price, policy,
promotion, safety advice or vehicle specification.
