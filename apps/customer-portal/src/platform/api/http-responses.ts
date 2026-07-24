import "server-only";
import {
  hardenPrivateResponse,
  PRIVATE_NO_STORE_HEADERS,
  privateEmpty,
  privateJson,
} from "@vfbiz/portal-session-core";

export { hardenPrivateResponse, privateEmpty, privateJson };

export function secureUpstreamResponse(upstream: Response): Response {
  const headers = new Headers(PRIVATE_NO_STORE_HEADERS);
  headers.set(
    "Content-Type",
    upstream.headers.get("content-type") ?? "application/json",
  );
  for (const name of ["etag", "x-correlation-id"]) {
    const value = upstream.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  headers.set("Vary", "Cookie");
  return new Response(upstream.body, { headers, status: upstream.status });
}
