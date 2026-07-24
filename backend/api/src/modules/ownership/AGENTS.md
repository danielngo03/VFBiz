# Ownership quarantine boundary

This directory is deliberately not a runtime NestJS context. Legacy ownership
tables are historical persistence only and are not proof that a customer owns a
vehicle.

## Invariants

- Do not add `index.ts`, a NestJS module, controller, provider or public export.
- Do not consume `OwnerVehicleAssociation`, `ServiceAppointmentProjection` or
  an untyped `externalVehicleRef` as verified ownership.
- Customer Garage remains self-reported and never grants Vision, recall,
  service, telematics or other owner-only access.
- Never persist or log raw VIN. Do not invent Vehicle Asset, tokenization,
  verification evidence or DMS/CRM data.

Materializing this boundary requires an approved provider contract, the
decision evidence from `VFBIZ-0036`, Privacy/Security/Data review, and a separate
controlled migration work item.

## Verify

Run the colocated quarantine architecture test, then API lint and typecheck.
The test prevents known source-level imports, Prisma delegate/property access and
raw SQL table references. It is not proof that raw VIN is absent end to end and
does not replace migration review, database permissions, runtime telemetry or a
privacy test once an authoritative ownership capability exists.
