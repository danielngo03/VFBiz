# Drupal workspace instructions

Read root `AGENTS.md` and this file. Read `README.md` only when scope or boundary
is relevant.

- Keep public content editable and translatable; do not hardcode editorial data.
- Prefer Drupal core, Twig and Single Directory Components for SSR.
- Treat SEO, cacheability, accessibility and responsive images as acceptance
  criteria, not cleanup.
- DDEV is the canonical local runtime. Composer is run at `drupal/`; Drupal's
  public document root is `drupal/web` and configuration truth is
  `drupal/config/sync` after installation.
- Site-level architecture and DDEV commands live in `drupal/docs/`; module tests
  stay beside the custom module. Do not commit database dumps, local settings or
  secrets.
- Catalog/price/location/customer facts come through approved API projections.
- A small presentational change may use fast lane. Content-model, permission,
  workflow, dependency or configuration changes are controlled.
- Bounded or controlled runtime work requires a current Git work item; a
  presentation-only fast change does not. DDEV is not the Drupal Devel module;
  Devel remains a development-only optional dependency.
