# Generation contract

The job validates against `contracts/ai/generation-job.schema.json` and pins:

- asset kind, one allowed use, task families, modalities, split role, profile and
  schema revision;
- approved seed/source references or synthetic fact namespaces;
- generator model, prompt, policy, temperature and deterministic seed;
- max records, input/output tokens and cost;
- intent/risk/locale/failure-mode coverage;
- unique shard ID, output prefix and lease;
- prohibited inputs including production PII and held-out evaluation.

One builder owns one shard. Shard contents are candidate-only and live in
approved object storage or a temporary gitignored path. Registry and release
manifest are single-writer resources controlled by the orchestrator/Data Owner.

`purpose`, `dataset_class` and `allowed_uses` are compatibility fields and must
not be written by new jobs. Multimodal is expressed through `modalities`; it is
never an allowed use. Evaluation, Golden and red-team families are locked before
generation and cannot be used as training seeds or descendants.

Generation should vary diacritics, typo, slang, code-switch and multi-turn while
preserving the expected policy outcome. It must not invent real price, policy,
promotion, safety advice or vehicle specification.
