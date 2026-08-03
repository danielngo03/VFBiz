import * as Crypto from "expo-crypto";

export function newIdempotencyKey(scope: string): string {
  if (!/^[a-z0-9-]+$/u.test(scope))
    throw new Error("Idempotency scope must be lowercase kebab-case.");
  return `${scope}:${Crypto.randomUUID()}`;
}
