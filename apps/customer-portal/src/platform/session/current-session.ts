import "server-only";
import { cookies } from "next/headers";
import { readCustomerPortalEnvironment } from "@/platform/config/environment";
import type { OpaqueCustomerSessionId } from "./contracts";
import { readSession } from "./redis-token-vault";

export async function currentCustomerSession() {
  const environment = readCustomerPortalEnvironment();
  const cookieStore = await cookies();
  const id = cookieStore.get(environment.CUSTOMER_SESSION_COOKIE_NAME)?.value;
  if (id === undefined) return null;
  const record = await readSession(id as OpaqueCustomerSessionId);
  return record === null ? null : { environment, record };
}
