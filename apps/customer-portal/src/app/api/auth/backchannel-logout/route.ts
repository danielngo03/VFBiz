import { privateEmpty, privateJson } from "@/platform/api/http-responses";
import { verifyBackchannelLogoutToken } from "@/platform/auth/oidc";
import {
  beginBackchannelLogoutToken,
  completeBackchannelLogoutToken,
  deleteAllSessions,
  deleteProviderSessions,
  releaseBackchannelLogoutToken,
} from "@/platform/session/redis-token-vault";

const MAX_LOGOUT_BODY_BYTES = 16 * 1024;

export async function POST(request: Request) {
  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.startsWith("application/x-www-form-urlencoded")) {
    return privateJson({ error: "unsupported_media_type" }, { status: 415 });
  }
  const declaredLength = Number(request.headers.get("content-length") ?? "0");
  if (declaredLength > MAX_LOGOUT_BODY_BYTES) {
    return privateJson({ error: "payload_too_large" }, { status: 413 });
  }
  const body = await request.text();
  if (Buffer.byteLength(body) > MAX_LOGOUT_BODY_BYTES) {
    return privateJson({ error: "payload_too_large" }, { status: 413 });
  }
  const logoutToken = new URLSearchParams(body).get("logout_token");
  if (logoutToken === null) {
    return privateJson({ error: "logout_token_required" }, { status: 400 });
  }
  let event: Awaited<ReturnType<typeof verifyBackchannelLogoutToken>>;
  try {
    event = await verifyBackchannelLogoutToken(logoutToken);
  } catch {
    return privateJson({ error: "invalid_logout_token" }, { status: 400 });
  }
  const claim = await beginBackchannelLogoutToken(event.jti);
  if (claim.state === "completed") return privateEmpty();
  if (claim.state === "in_progress") {
    return privateJson(
      { error: "logout_in_progress" },
      { headers: { "Retry-After": "1" }, status: 503 },
    );
  }
  try {
    if (event.providerSessionId !== undefined) {
      await deleteProviderSessions(event.providerSessionId);
    } else if (event.subject !== undefined) {
      await deleteAllSessions(event.subject);
    }
    if (!(await completeBackchannelLogoutToken(event.jti, claim.token))) {
      throw new Error("Back-channel logout claim expired.");
    }
    return privateEmpty();
  } catch {
    await releaseBackchannelLogoutToken(event.jti, claim.token).catch(
      () => undefined,
    );
    return privateJson(
      { error: "logout_retry_required" },
      { headers: { "Retry-After": "1" }, status: 503 },
    );
  }
}
