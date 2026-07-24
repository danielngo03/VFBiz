import "server-only";
import { refreshTokens } from "@/platform/auth/oidc";
import { readCustomerPortalEnvironment } from "@/platform/config/environment";
import { currentCustomerSession } from "@/platform/session/current-session";
import {
  acquireRefreshLease,
  deleteSession,
  readSession,
  releaseRefreshLease,
  writeSession,
} from "@/platform/session/redis-token-vault";

async function usableToken() {
  const active = await currentCustomerSession();
  if (active === null) return null;
  if (active.record.tokenSet.expiresAt.getTime() > Date.now() + 30_000) {
    return active.record.tokenSet.accessToken;
  }
  const refreshToken = active.record.tokenSet.refreshToken;
  if (refreshToken === undefined) return null;
  const lease = await acquireRefreshLease(active.record.session.id);
  if (lease === null) {
    for (let attempt = 0; attempt < 5; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 100));
      const updated = await readSession(active.record.session.id);
      if (
        updated !== null &&
        updated.tokenSet.expiresAt.getTime() > Date.now() + 5_000
      ) {
        return updated.tokenSet.accessToken;
      }
    }
    return null;
  }
  try {
    const refreshed = await refreshTokens(refreshToken);
    const revision = await writeSession(
      active.record.session,
      {
        accessToken: refreshed.access_token,
        expiresAt: new Date(Date.now() + refreshed.expires_in * 1_000),
        refreshToken: refreshed.refresh_token ?? refreshToken,
      },
      { expectedRevision: active.record.revision },
    );
    if (revision === null) return null;
    return refreshed.access_token;
  } catch {
    await deleteSession(
      active.record.session.id,
      active.record.session.subject,
      active.record.session.providerSessionId,
    );
    return null;
  } finally {
    await releaseRefreshLease(active.record.session.id, lease);
  }
}

export async function customerApiRequest(
  path: string,
  init: Omit<RequestInit, "cache" | "credentials" | "redirect" | "signal"> = {},
): Promise<Response> {
  if (path !== "/api/v1/me" && !path.startsWith("/api/v1/me/")) {
    throw new Error("Customer BFF path is outside the reviewed boundary.");
  }
  const token = await usableToken();
  if (token === null) {
    return Response.json({ error: "session_required" }, { status: 401 });
  }
  const environment = readCustomerPortalEnvironment();
  const headers = new Headers(init.headers);
  headers.set("accept", "application/json");
  headers.set("authorization", `Bearer ${token}`);
  return fetch(new URL(path, environment.CUSTOMER_API_BASE_URL), {
    ...init,
    cache: "no-store",
    credentials: "omit",
    headers,
    redirect: "error",
    signal: AbortSignal.timeout(10_000),
  });
}

export function customerApiGet(path: string): Promise<Response> {
  return customerApiRequest(path, { method: "GET" });
}
