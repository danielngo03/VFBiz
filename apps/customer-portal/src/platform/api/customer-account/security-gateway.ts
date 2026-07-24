import "server-only";

import { customerApiRequest } from "@/platform/api/customer-api";
import {
  customerSessionsSchema,
  identitySecuritySchema,
  revokeAllSessionsResultSchema,
  revokeSessionResultSchema,
  type CustomerIdentitySecurity,
  type CustomerSession,
  type RevokeAllSessionsResult,
  type RevokeSessionResult,
} from "./security-contracts";
import { parseAccountResponse } from "./response";

export { CustomerAccountApiError } from "./response";

export async function getIdentitySecurity(): Promise<CustomerIdentitySecurity> {
  return parseAccountResponse(
    await customerApiRequest("/api/v1/me/sessions/security", { method: "GET" }),
    identitySecuritySchema,
  );
}

export async function listCustomerSessions(): Promise<CustomerSession[]> {
  return parseAccountResponse(
    await customerApiRequest("/api/v1/me/sessions", { method: "GET" }),
    customerSessionsSchema,
  );
}

export async function revokeCustomerSession(
  sessionId: string,
): Promise<RevokeSessionResult> {
  return parseAccountResponse(
    await customerApiRequest(
      `/api/v1/me/sessions/${encodeURIComponent(sessionId)}`,
      { method: "DELETE" },
    ),
    revokeSessionResultSchema,
  );
}

export async function revokeAllCustomerSessions(): Promise<RevokeAllSessionsResult> {
  return parseAccountResponse(
    await customerApiRequest("/api/v1/me/sessions", { method: "DELETE" }),
    revokeAllSessionsResultSchema,
  );
}
