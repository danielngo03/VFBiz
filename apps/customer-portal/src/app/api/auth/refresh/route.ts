import { privateEmpty, privateJson } from "@/platform/api/http-responses";
import { refreshTokens } from "@/platform/auth/oidc";
import { currentCustomerSession } from "@/platform/session/current-session";
import {
  acquireRefreshLease,
  deleteSession,
  releaseRefreshLease,
  writeSession,
} from "@/platform/session/redis-token-vault";
import {
  hasValidCsrfToken,
  hasValidRequestOrigin,
} from "@/platform/session/request-security";

export async function POST(request: Request) {
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
  const refreshToken = active.record.tokenSet.refreshToken;
  if (refreshToken === undefined) {
    await deleteSession(
      active.record.session.id,
      active.record.session.subject,
      active.record.session.providerSessionId,
    );
    const response = privateJson(
      { error: "refresh_unavailable" },
      { status: 401 },
    );
    response.cookies.delete(active.environment.CUSTOMER_SESSION_COOKIE_NAME);
    return response;
  }
  const lease = await acquireRefreshLease(active.record.session.id);
  if (lease === null) {
    return privateJson(
      { error: "refresh_in_progress" },
      { headers: { "Retry-After": "1" }, status: 409 },
    );
  }
  try {
    const token = await refreshTokens(refreshToken);
    const revision = await writeSession(
      active.record.session,
      {
        accessToken: token.access_token,
        expiresAt: new Date(Date.now() + token.expires_in * 1_000),
        refreshToken: token.refresh_token ?? refreshToken,
      },
      { expectedRevision: active.record.revision },
    );
    if (revision === null) {
      const response = privateJson(
        { error: "session_revoked" },
        { status: 401 },
      );
      response.cookies.delete(active.environment.CUSTOMER_SESSION_COOKIE_NAME);
      return response;
    }
    return privateEmpty();
  } catch {
    await deleteSession(
      active.record.session.id,
      active.record.session.subject,
      active.record.session.providerSessionId,
    );
    const response = privateJson({ error: "refresh_failed" }, { status: 401 });
    response.cookies.delete(active.environment.CUSTOMER_SESSION_COOKIE_NAME);
    return response;
  } finally {
    await releaseRefreshLease(active.record.session.id, lease);
  }
}
