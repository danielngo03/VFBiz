import "server-only";

import { customerApiRequest } from "@/platform/api/customer-api";
import {
  customerProfileSchema,
  profileEtagSchema,
  type CustomerProfile,
  type CustomerProfilePatch,
} from "./profile-contracts";
import {
  CustomerAccountApiError,
  parseAccountResponse,
} from "./response";

export { CustomerAccountApiError } from "./response";

export async function getCustomerProfile(): Promise<{
  readonly etag: string;
  readonly profile: CustomerProfile;
}> {
  const response = await customerApiRequest("/api/v1/me", { method: "GET" });
  const profile = await parseAccountResponse(response, customerProfileSchema);
  const etag = profileEtagSchema.safeParse(response.headers.get("etag"));
  if (!etag.success) {
    throw new CustomerAccountApiError(
      502,
      "PROFILE_ETAG_MISSING",
      response.headers.get("x-correlation-id"),
    );
  }
  return { etag: etag.data, profile };
}

export async function updateCustomerProfile(
  patch: CustomerProfilePatch,
  expectedEtag: string,
): Promise<{ readonly etag: string; readonly profile: CustomerProfile }> {
  const response = await customerApiRequest("/api/v1/me", {
    body: JSON.stringify(patch),
    headers: {
      "content-type": "application/json",
      "if-match": expectedEtag,
    },
    method: "PATCH",
  });
  const profile = await parseAccountResponse(response, customerProfileSchema);
  const etag = profileEtagSchema.safeParse(response.headers.get("etag"));
  if (!etag.success) {
    throw new CustomerAccountApiError(
      502,
      "PROFILE_ETAG_MISSING",
      response.headers.get("x-correlation-id"),
    );
  }
  return { etag: etag.data, profile };
}
