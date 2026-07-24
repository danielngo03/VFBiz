import "server-only";
import { NextResponse } from "next/server";

export const PRIVATE_NO_STORE_HEADERS = {
  "Cache-Control": "private, no-store",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
} as const;

export function privateJson(
  body: unknown,
  init: { readonly headers?: HeadersInit; readonly status?: number } = {},
): NextResponse {
  const headers = new Headers(init.headers);
  for (const [name, value] of Object.entries(PRIVATE_NO_STORE_HEADERS))
    headers.set(name, value);
  return NextResponse.json(body, { ...init, headers });
}

export function privateEmpty(status = 204): NextResponse {
  return new NextResponse(null, {
    headers: PRIVATE_NO_STORE_HEADERS,
    status,
  });
}

export function hardenPrivateResponse<T extends Response>(response: T): T {
  for (const [name, value] of Object.entries(PRIVATE_NO_STORE_HEADERS))
    response.headers.set(name, value);
  return response;
}
