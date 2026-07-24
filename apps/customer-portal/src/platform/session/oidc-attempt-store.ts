import "server-only";
import { randomBytes, randomUUID } from "node:crypto";
import {
  customerSessionKey,
  customerSessionRedis,
  decryptVaultRecord,
  encryptVaultRecord,
} from "./redis-vault-runtime";

const ATTEMPT_TTL_SECONDS = 600;

interface OidcAttempt {
  readonly codeVerifier: string;
  readonly nonce: string;
  readonly returnTo: string;
  readonly state: string;
}

export function newAttempt() {
  return {
    attemptId: randomUUID(),
    codeVerifier: randomBytes(48).toString("base64url"),
    nonce: randomBytes(24).toString("base64url"),
    state: randomBytes(24).toString("base64url"),
  };
}

export async function saveAttempt(
  attemptId: string,
  attempt: OidcAttempt,
): Promise<void> {
  await customerSessionRedis().set(
    customerSessionKey("oidc-attempt", attemptId),
    encryptVaultRecord(attempt),
    "EX",
    ATTEMPT_TTL_SECONDS,
  );
}

export async function consumeAttempt(
  attemptId: string,
): Promise<OidcAttempt | null> {
  const value = await customerSessionRedis().getdel(
    customerSessionKey("oidc-attempt", attemptId),
  );
  return value === null ? null : decryptVaultRecord<OidcAttempt>(value);
}
