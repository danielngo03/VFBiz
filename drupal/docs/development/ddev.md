---
id: drupal-ddev-runbook
title: DDEV local development
status: active
owner_role: engineering-lead
scope: drupal
when_to_read:
  - ddev
  - local-development
  - drupal-config
tags:
  - drupal
  - ddev
revision: 3
review_date: 2026-08-22
supersedes: []
---

# DDEV local development

DDEV is the local container environment. It is not the Drupal Devel module.

```bash
cd drupal
ddev start
ddev composer install
ddev drush status
```

Install the committed configuration into a clean database:

```bash
ddev drush site:install --existing-config -y
```

For an intentional configuration change:

```bash
ddev drush config:export -y
ddev drush config:status
```

Review the config diff before commit. Local URLs, credentials, database dumps
and secrets never enter `config/sync` or Git. Deployment uses `drush deploy` in
the target environment; a local successful deploy command is not production
release approval.

Focused quality checks:

```bash
ddev composer validate --strict
ddev composer audit
ddev exec vendor/bin/phpcs
ddev exec vendor/bin/phpstan analyse
ddev exec vendor/bin/phpunit
ddev drush config:status
```

The project does not require the Drupal Devel module. If a developer adds it
for local debugging, it must stay development-only and must not become a runtime
dependency or exported production configuration.
