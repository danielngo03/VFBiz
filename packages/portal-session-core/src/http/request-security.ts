import "server-only";
import { randomBytes, timingSafeEqual } from "node:crypto";

export function newCsrfToken(): string {
  return randomBytes(32).toString("base64url");
}

export function hasExactOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  return origin !== null && origin === new URL(request.url).origin;
}

export function hasValidCsrfToken(
  request: Request,
  expectedToken: string,
): boolean {
  const supplied = request.headers.get("x-csrf-token");
  if (supplied === null) return false;
  const expected = Buffer.from(expectedToken);
  const actual = Buffer.from(supplied);
  return (
    expected.byteLength === actual.byteLength &&
    timingSafeEqual(expected, actual)
  );
}
