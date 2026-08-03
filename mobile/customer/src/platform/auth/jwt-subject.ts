function decodeBase64Url(value: string): string {
  const normalized = value.replace(/-/gu, "+").replace(/_/gu, "/");
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
  return globalThis.atob(padded);
}

interface IdentityClaims {
  sub?: unknown;
  iss?: unknown;
  aud?: unknown;
  azp?: unknown;
  exp?: unknown;
  nonce?: unknown;
}

function claimsFromIdToken(idToken: string): IdentityClaims {
  const payload = idToken.split(".")[1];
  if (!payload) throw new Error("Identity token payload is invalid.");
  return JSON.parse(decodeBase64Url(payload)) as IdentityClaims;
}

export function subjectFromIdToken(idToken: string | undefined): string {
  if (!idToken) throw new Error("Identity token is required to bind local data.");
  const decoded = claimsFromIdToken(idToken);
  if (typeof decoded.sub !== "string" || decoded.sub === "")
    throw new Error("Identity token subject is missing.");
  return decoded.sub;
}

export function validateIdentityToken(
  idToken: string | undefined,
  expected: { issuer: string; clientId: string; nonce?: string; now?: number },
): string {
  if (!idToken) throw new Error("Identity token is required.");
  const claims = claimsFromIdToken(idToken);
  if (claims.iss !== expected.issuer)
    throw new Error("Identity token issuer does not match runtime authority.");
  const audiences = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (!audiences.includes(expected.clientId))
    throw new Error("Identity token audience does not match this app.");
  if (audiences.length > 1 && claims.azp !== expected.clientId)
    throw new Error("Identity token authorized party does not match this app.");
  const nowSeconds = Math.floor((expected.now ?? Date.now()) / 1000);
  if (typeof claims.exp !== "number" || claims.exp <= nowSeconds)
    throw new Error("Identity token has expired.");
  if (expected.nonce !== undefined && claims.nonce !== expected.nonce)
    throw new Error("Identity token nonce does not match the authorization request.");
  return subjectFromIdToken(idToken);
}
