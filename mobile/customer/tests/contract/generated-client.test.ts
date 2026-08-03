import type { paths } from "@vfbiz/api-client";
import { customerResourcePaths } from "../../src/platform/api/customer-contract";

type ProfileOperation = paths["/api/v1/me"]["get"];
const profileOperationExists: ProfileOperation extends never ? false : true = true;

test("customer resources stay bound to generated public paths", () => {
  expect(profileOperationExists).toBe(true);
  expect(customerResourcePaths).toEqual({
    profile: "/api/v1/me",
    sessions: "/api/v1/me/sessions",
    consents: "/api/v1/me/consents",
    garage: "/api/v1/me/vehicles",
    security: "/api/v1/me/sessions/security",
    dataRequests: "/api/v1/me/data-requests",
    models: "/api/v1/vehicles/models",
  });
});
