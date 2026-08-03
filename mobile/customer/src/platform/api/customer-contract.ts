import type { components, paths } from "@vfbiz/api-client";

type JsonResponse<Operation extends { responses: unknown }, Status extends number> =
  Operation["responses"] extends Record<Status, { content: { "application/json": infer Body } }>
    ? Body
    : never;

export type CustomerProfile = JsonResponse<
  paths["/api/v1/me"]["get"],
  200
>;
export type CustomerSessions = JsonResponse<
  paths["/api/v1/me/sessions"]["get"],
  200
>;
export type CustomerConsents = JsonResponse<
  paths["/api/v1/me/consents"]["get"],
  200
>;
export type CustomerGarage = JsonResponse<
  paths["/api/v1/me/vehicles"]["get"],
  200
>;
export type CustomerSecurity = JsonResponse<
  paths["/api/v1/me/sessions/security"]["get"],
  200
>;
export type CustomerDataRequests = JsonResponse<
  paths["/api/v1/me/data-requests"]["get"],
  200
>;
export type VehicleModels = JsonResponse<
  paths["/api/v1/vehicles/models"]["get"],
  200
>;
export type CreateGarageEntry = components["schemas"]["CreateCustomerGarageEntry"];
export type GarageEntry = components["schemas"]["CustomerGarageEntry"];

export const customerResourcePaths = {
  profile: "/api/v1/me",
  sessions: "/api/v1/me/sessions",
  consents: "/api/v1/me/consents",
  garage: "/api/v1/me/vehicles",
  security: "/api/v1/me/sessions/security",
  dataRequests: "/api/v1/me/data-requests",
  models: "/api/v1/vehicles/models",
} as const satisfies Record<string, keyof paths>;
