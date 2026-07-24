import "server-only";
import { randomBytes, randomUUID } from "node:crypto";
import type { OpaquePortalSessionId } from "./contracts";

export function newOpaqueSessionId(): OpaquePortalSessionId {
  return randomBytes(32).toString("base64url") as OpaquePortalSessionId;
}

export function newPkceAttemptIdentifiers() {
  return {
    attemptId: randomUUID(),
    codeVerifier: randomBytes(48).toString("base64url"),
    nonce: randomBytes(24).toString("base64url"),
    state: randomBytes(24).toString("base64url"),
  };
}
