---
id: dependency-risk-register
title: Production dependency risk register
status: active
owner_role: security-owner
scope: cross-system
when_to_read:
  - dependency-policy
  - staging-readiness
tags:
  - supply-chain
  - security
  - staging
revision: 1
review_date: 2026-08-12
supersedes: []
---

# Production dependency risk register

> Evidence snapshot: `npm audit --omit=dev --json`, observed 2026-07-29.
> Fourteen high findings and zero critical findings remain. This document does
> not accept risk; unresolved rows block staging unless the Security Owner
> records a separate, expiring exception.
>
> Machine authority: `dependency-risk-snapshot.json` is bound to the SHA-256 of
> `package-lock.json`. `npm run dependency-risk:check` rejects lockfile drift;
> `npm run dependency-risk:live-check` additionally compares the current audit
> and fails while an unexcepted high or critical package remains.

| Advisory/family | Observed path and version | Reachability | Owner / due | Disposition |
| --- | --- | --- | --- | --- |
| `GHSA-8pvw-jcv7-9cmj`, `GHSA-83w8-p2f5-377r` — `@fastify/static` | API direct `9.3.0`; NestJS subtree resolves the same version. Fixed line begins at `10.1.2`. | API documentation/static plugin is composed from NestJS dependencies. Production documentation is disabled, which reduces exposure but does not remove vulnerable code from the runtime graph. | `api-foundation` / 2026-08-05 | Test the supported `10.1.2+` line with NestJS 11; staging-blocking. |
| `GHSA-c96f-x56v-gq3h` — `find-my-way` | NestJS/Fastify subtree `9.6.0`; fixed `9.7.0`. Root override has not replaced this subtree. | Fastify request routing is directly production-reachable, including HTTP/2 behavior at the service or ingress boundary. | `api-foundation` / 2026-08-05 | Resolve the direct/transitive lock graph to `9.7.0+` and run full API regression; staging-blocking. |
| `GHSA-pm4m-ph32-ghv5` — `@nestjs/swagger` / `js-yaml` | Swagger subtree `js-yaml 5.2.1`; fixed `5.2.2`. | Swagger generation consumes repository-controlled definitions at build/startup; no untrusted request YAML is accepted by an application endpoint. | `api-foundation` / 2026-08-05 | Upgrade through a Swagger-compatible resolution; no silent framework downgrade. |
| `GHSA-qx2v-qp2m-jg93`, `GHSA-6g55-p6wh-862q`, `GHSA-r28c-9q8g-f849` — `next` / `postcss` | Next `16.2.12` contains PostCSS `8.4.31`; npm reports no safe stable Next upgrade and suggests an invalid downgrade. | Customer and Workforce portals are public build/runtime surfaces; CSS/source-map processing is part of the framework toolchain. | `customer-web-experience`, `workforce-experience` / 2026-08-05 | Track a fixed supported Next line or test a compatible transitive resolution; staging-blocking. |
| `GHSA-f88m-g3jw-g9cj` — `next` / `sharp` | Next `16.2.12` optional dependency resolves Sharp `0.34.5`; fixed line begins at `0.35.0`. | Image processing can be production-reachable through optimized image paths. | `customer-web-experience`, `workforce-experience` / 2026-08-05 | Use a Next-supported Sharp release and run image regression; staging-blocking. |
| `gcp-metadata` / `gaxios` | OpenTelemetry GCP detector resolves `gcp-metadata 8.1.4` → `gaxios 7.1.3`. | Startup resource detection is not supplied directly by customer input, but performs metadata network and cleanup operations. | `reliability-engineering` / 2026-08-12 | Upgrade the owning detector or compatible `gaxios`; verify metadata timeout and egress policy. |
| `GHSA-mh99-v99m-4gvg` and affected `glob` / `minimatch` / `rimraf` paths | Reachable transitively through static tooling and GCP metadata cleanup; exact paths are preserved by the lockfile audit. | Direct customer control is limited, but unbounded pattern/resource processing remains a supply-chain risk. | `api-foundation`, `reliability-engineering` / 2026-08-12 | Remediate by upgrading each owning parent, not by a global incompatible override. |

## Release policy

- `npm audit fix --force` is forbidden.
- npm suggestions that downgrade NestJS, Next or Swagger are not accepted as
  remediation.
- A temporary exception requires advisory identifiers, reachability evidence,
  compensating controls, owner, expiry and a removal work item.
- CI must re-run the production audit from the lockfile. A new critical finding
  or an unregistered high finding fails the release gate.
- This register explains the point-in-time assessment. The lockfile-bound JSON
  snapshot and live audit comparison are the machine-observed evidence.
- No exception is currently approved. Every row above remains open.
