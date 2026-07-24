import { privateEmpty, privateJson } from "@/platform/api/http-responses";
import { currentCustomerSession } from "@/platform/session/current-session";
import { revokeOrEnqueueProviderToken } from "@/platform/session/provider-revocation-reconciler";
import { deleteSession } from "@/platform/session/redis-token-vault";
import {
  hasValidCsrfToken,
  hasValidRequestOrigin,
} from "@/platform/session/request-security";

export async function POST(request: Request) {
  if (!hasValidRequestOrigin(request)) {
    return privateJson({ error: "invalid_origin" }, { status: 403 });
  }
  const active = await currentCustomerSession();
  if (active === null) return privateEmpty();
  if (!hasValidCsrfToken(request, active.record.session)) {
    return privateJson({ error: "invalid_csrf_token" }, { status: 403 });
  }
  await deleteSession(
    active.record.session.id,
    active.record.session.subject,
    active.record.session.providerSessionId,
  );
  const providerReconciliation = await revokeOrEnqueueProviderToken({
    providerSessionId: active.record.session.providerSessionId,
    refreshToken: active.record.tokenSet.refreshToken,
  });
  const response = privateJson({ providerReconciliation });
  response.cookies.delete(active.environment.CUSTOMER_SESSION_COOKIE_NAME);
  return response;
}
