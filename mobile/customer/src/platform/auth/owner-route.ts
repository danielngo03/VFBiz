import type { AuthStatus } from "../../domain/session/session";

export type OwnerRouteDecision = "loading" | "sign-in" | "owner";

export function ownerRouteDecision(
  status: AuthStatus,
  hasCredential: boolean,
): OwnerRouteDecision {
  if (["restoring", "authenticating", "refreshing"].includes(status))
    return "loading";
  return status === "authenticated" && hasCredential ? "owner" : "sign-in";
}
