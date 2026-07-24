---
id: staging-mvp
title: Staging MVP Account, Customer Chatbot và EV Trip Planner
status: superseded
owner_role: product-owner
scope: cross-system
when_to_read:
  - staging-mvp
  - account
  - chatbot
  - trip
tags:
  - product
  - account
  - ai
  - trip
revision: 3
review_date: 2026-08-22
supersedes: []
---

# Staging MVP: Account, Customer Chatbot and EV Trip Planner

> Tài liệu lịch sử. Phạm vi delivery hiện tại được thay bởi
> `docs/product/customer-chatbot.md`. Account và Trip Planner vẫn ở roadmap
> tương lai, không còn được context resolver chọn cho Chatbot V6.

## Outcome

By the staging acceptance gate, a customer can complete the account lifecycle,
manage consent and an unverified garage, ask grounded vehicle/policy/charging
questions, and obtain a deterministic EV trip plan. Workforce users authenticate
with a separate realm and operate within audited roles.

## Included

- Email registration and verification, password recovery, TOTP MFA, session
  revoke, profile, consent, export/delete request, and garage.
- Public and authenticated customer chatbot profiles with citation, refusal,
  subject isolation, and read-only tools.
- Vehicle energy, charging station, connector, tariff, Google Maps adapter, and
  deterministic route/energy/charging/time/cost planning.
- Customer Portal, Operations Admin, and Drupal public entry/widget integration.
- OpenAPI-generated client, negative authorization, AI evaluation, E2E,
  provider-outage, load/cost, and rollback evidence.

## Excluded

Real payment/deposit, DMS/VIN verification, phone OTP, social/passwordless login,
mobile UI, employee assistant, side-effecting AI tools, fine-tuning, production
data migration, production HA/DR, and production release.

## Data rules

Staging uses synthetic, versioned data only. Unverified vehicles remain
`unverified`. Sources for vehicle, station, tariff, knowledge, and evaluation
carry an owner, provenance/license, revision, effective date, classification,
ACL, and freshness. Missing or stale evidence produces an unavailable state,
refusal, or explicit confidence warning; it never becomes an invented fact.

## Product gates

- Factual AI evaluation responses: valid citation or refusal, 100%.
- Citation correctness and groundedness: at least 95%.
- Cross-subject, cross-ACL, and PII leakage: zero in the security suite.
- Account API p95 at most 500 ms; cached read p95 at most 300 ms.
- Internal trip calculation p95 at most 800 ms; provider flow at most 3 s.
- Chat first token p95 at most 3 s; full answer p95 at most 10 s.

These are staging gates, not production claims.
