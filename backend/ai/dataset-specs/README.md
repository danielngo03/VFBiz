# ViVi dataset specifications

This directory contains small, reviewable specifications only. Dataset payloads,
job instances, scan reports and release evidence belong in content-addressed
object storage with PostgreSQL registry pointers; they must not be committed to
Git.

## Authorities

- `catalog/sources/public`: one human-reviewable source catalog entry per
  upstream source. A catalog entry does not grant fetch, purpose or release
  approval.
- `catalog/portfolios`: capability portfolios that reference source IDs without
  copying source metadata.
- `catalog/capabilities`: candidate product-to-source coverage. Product
  contracts and immutable releases are introduced only when their runtime
  consumer exists.
- `evaluation`: Golden/evaluation suite definitions, rubrics and taxonomies.
- `export-profiles`: deterministic export formats. Export never submits a
  training job.
- `evidence-index`: compact immutable references to historical generated
  evidence. New evidence is stored in the registry/object store, not here.

`catalog/sources/index.json` is the deterministic discovery surface. Each entry
resolves to one independently reviewable source manifest; no aggregate file
duplicates source metadata or approval state.

## Invariants

- No `wave-*`, date, provider or model name defines an active architecture
  boundary.
- Golden, evaluation and red-team families never become training, retrieval or
  synthetic seeds.
- Public data never becomes factual VinFast knowledge without approved
  first-party evidence and fact binding.
- Repository state never implies human approval. Source and purpose gates remain
  fail-closed.
- Do not create empty product, domain-pack or modality folders ahead of a real
  contract and consumer.
