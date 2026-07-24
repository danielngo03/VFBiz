import "server-only";
import {
  hasExactOrigin,
  hasValidCsrfToken as hasMatchingCsrfToken,
  newCsrfToken,
} from "@vfbiz/portal-session-core";
import type { CustomerBffSession } from "./contracts";

export { newCsrfToken };

export function hasValidRequestOrigin(request: Request): boolean {
  return hasExactOrigin(request);
}

export function hasValidCsrfToken(
  request: Request,
  session: CustomerBffSession,
): boolean {
  return hasMatchingCsrfToken(request, session.csrfToken);
}
