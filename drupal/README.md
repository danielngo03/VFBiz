# Web Experience & CMS workspace

Status: Drupal 11/DDEV runtime bootstrap is present; verify the current Git work
item before changing runtime behavior.

Ownership: public VI/EN SSR website, CMS, SEO, menus, reusable content,
editorial workflow, accessibility, performance and web image metadata.

Drupal will not own CIAM, customer profiles, leads as system of record,
transactions, payment, private documents, AI/RAG or the public API contract.

The first active module is `vfbiz_ai_client`, a presentational entry point only.
It never calls an AI provider or stores chat/customer state. Runtime setup and
quality commands are documented in `docs/development/ddev.md`.
