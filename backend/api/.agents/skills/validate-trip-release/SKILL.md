---
name: validate-trip-release
description: Validate a VFBiz EV Trip Planner candidate across deterministic energy, charging, Maps cost controls, stale data, failure behavior and staging release evidence. Use before a Trip Planner staging or production release decision.
---

# Validate a Trip Planner release

1. Resolve the active work item/release acceptance and named Release Owner. Pin
   route adapter, vehicle energy profile, Location/EVSE/Connector, availability
   observation, tariff, reliability, algorithm and cache-policy revisions used
   by the candidate.
2. Run unit/property cases for units, reserve SOC, arrival/target SOC, charging curves, incompatible connectors and invalid input.
3. Exercise routes needing zero, one and multiple stops, plus no feasible route.
   Include station closure, stale availability, ambiguous tariff, timezone/DST
   and degraded battery/environment inputs. Verify totals equal the sum of
   travel, charging and cost segments within declared tolerances.
4. Test Google timeout, quota exhaustion, invalid response and unavailable
   mode. Confirm use-case-specific field-mask allowlists, Autocomplete session
   tokens, key restrictions, attribution, deduplication, rate limits, provider
   storage policy and budget alerts.
5. Use record/replay for load tests. Limit real-provider smoke tests with an explicit budget cap.
6. Verify exact origin/destination is absent from logs and analytics, persisted
   location follows the approved retention/pseudonymization policy, and no
   home/work inference occurs without consent.
7. Verify UI/API expose source revision, freshness, confidence range and an honest unavailable state instead of invented precision.
8. Capture latency, cache hit, provider request/cost and failure evidence.
   Compare against versioned SLO/cost acceptance from the active work item or
   release policy; never invent or silently reuse an expired target.
9. Produce an immutable release report with candidate/base revision, observed
   checks, deviations, residual risks and rollback reference for the Release
   Owner. Do not self-approve, promote or deploy.

## Required gates

- Required performance, availability and cost targets are explicit, current and
  observed under the declared workload. Missing acceptance is `needs-decision`.
- No stale or missing source is silently presented as a verified trip fact.
- Same-cause retry and review/fix cycles remain within repository limits.

## Realistic trigger scenarios

- Positive: review a staging candidate that changes the energy estimator,
  Google Routes adapter, charging-data revision or constrained planner.
- Positive: verify a release after a tariff, connector or availability
  projection migration.
- Negative: do not trigger for a local refactor that only renames an internal
  purge helper and does not alter planning behavior, contract or release.
- Negative: do not use this skill to approve provider terms, privacy risk or
  production release; return evidence to the named human authority.
