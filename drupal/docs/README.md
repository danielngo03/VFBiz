---
id: drupal-workspace-guide
title: Drupal workspace guide
status: active
owner_role: engineering-lead
scope: drupal
when_to_read:
  - drupal-boundary
  - drupal-integration
tags:
  - drupal
  - cms
revision: 3
review_date: 2026-08-22
supersedes: []
---

# Drupal workspace guide

Drupal owns public SSR/CMS/SEO, VI/EN editorial workflow and web image metadata.
It does not own customer identity, transactions, structured vehicle/trip truth,
chat sessions or AI execution.

## Current baseline

```text
.ddev/                  local container runtime
composer.json           dependency source
composer.lock           reproducible dependency resolution
config/sync/            site desired state after install
phpcs.xml.dist          Drupal/DrupalPractice rules for owned PHP
recipes/                one-time capability bootstrap
docs/                   workspace guides and runbooks
tests/                  site-level/cross-module tests only
web/modules/custom/     VFBiz modules and colocated tests
web/themes/custom/      Twig/SDC design system
```

The site currently uses Drupal 11.4.4, PHP 8.4, MariaDB 11.8 and DDEV. The clean
configuration baseline enables VI/EN, media, responsive images, workflows and
content moderation. `config/sync` is the desired state after installation.

Custom UI belongs in Single Directory Components. The current
`vfbiz_ai_client` module renders a presentational client entry and dispatches an
integration event; it does not call models, store PII or become an API facade.
Catalog, account, chatbot and trip integrations are not complete until their
API contracts and end-to-end evidence exist.

Use [DDEV local development](development/ddev.md) for install and verification.
