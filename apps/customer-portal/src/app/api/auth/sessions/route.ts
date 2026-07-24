import { privateJson } from "@/platform/api/http-responses";
import { currentCustomerSession } from "@/platform/session/current-session";
import { revokeOrEnqueueProviderToken } from "@/platform/session/provider-revocation-reconciler";
import {
  deleteAllSessions,
  listSessions,
} from "@/platform/session/redis-token-vault";
import {
  hasValidCsrfToken,
  hasValidRequestOrigin,
} from "@/platform/session/request-security";

export async function GET() {
  const active = await currentCustomerSession();
  if (active === null) {
    return privateJson({ error: "session_required" }, { status: 401 });
  }
  const sessions = await listSessions(active.record.session.subject);
  return privateJson(
    sessions.map(({ session }) => ({
      authenticatedAt: session.authenticatedAt,
      deviceLabel: session.deviceLabel,
      expiresAt: session.expiresAt,
      id: session.id,
      isCurrent: session.id === active.record.session.id,
      lastSeenAt: session.lastSeenAt,
      mfaSatisfied: session.mfaSatisfied,
      networkHint: session.networkHint,
      userAgentSummary: session.userAgentSummary,
    })),
  );
}

export async function DELETE(request: Request) {
  if (!hasValidRequestOrigin(request)) {
    return privateJson({ error: "invalid_origin" }, { status: 403 });
  }
  const active = await currentCustomerSession();
  if (active === null) {
    return privateJson({ error: "session_required" }, { status: 401 });
  }
  if (!hasValidCsrfToken(request, active.record.session)) {
    return privateJson({ error: "invalid_csrf_token" }, { status: 403 });
  }
  const sessions = await listSessions(active.record.session.subject);
  const revokedCount = await deleteAllSessions(active.record.session.subject);
  const providerResults = await Promise.all(
    sessions.map(({ session, tokenSet }) =>
      revokeOrEnqueueProviderToken({
        providerSessionId: session.providerSessionId,
        refreshToken: tokenSet.refreshToken,
      }),
    ),
  );
  const providerReconciliation = providerResults.includes("retry_required")
    ? "retry_required"
    : providerResults.includes("pending")
      ? "pending"
      : "confirmed";
  const response = privateJson({
    providerReconciliation,
    revokedCount,
  });
  response.cookies.delete(active.environment.CUSTOMER_SESSION_COOKIE_NAME);
  return response;
}
