const DEFAULT_CUSTOMER_RETURN_TO = "/account";
const RETURN_TO_BASE_URL = "https://customer-portal.invalid";
const MAX_RETURN_TO_LENGTH = 2_048;
const MAX_DECODE_PASSES = 5;

function hasUnsafePathSyntax(value: string): boolean {
  return (
    value.includes("\\") ||
    /[\u0000-\u001f\u007f]/u.test(value) ||
    value.startsWith("//")
  );
}

/**
 * Accepts only a same-origin, root-relative portal path. Each encoded form is
 * checked so nested encodings cannot smuggle a slash or backslash past the
 * first validation pass and become an external redirect later.
 */
export function normalizeCustomerReturnTo(value: string): string | null {
  if (
    value.length === 0 ||
    value.length > MAX_RETURN_TO_LENGTH ||
    !value.startsWith("/")
  ) {
    return null;
  }

  let decoded = value;
  for (let pass = 0; pass < MAX_DECODE_PASSES; pass += 1) {
    if (hasUnsafePathSyntax(decoded)) return null;
    let next: string;
    try {
      next = decodeURIComponent(decoded);
    } catch {
      return null;
    }
    if (next === decoded) break;
    decoded = next;
  }
  if (hasUnsafePathSyntax(decoded) || /%(?:2f|5c)/iu.test(decoded)) return null;

  let resolved: URL;
  try {
    resolved = new URL(value, RETURN_TO_BASE_URL);
  } catch {
    return null;
  }
  if (
    resolved.origin !== RETURN_TO_BASE_URL ||
    resolved.username !== "" ||
    resolved.password !== ""
  ) {
    return null;
  }
  return `${resolved.pathname}${resolved.search}${resolved.hash}`;
}

export function customerReturnToOrDefault(value: string | null): string {
  return value === null
    ? DEFAULT_CUSTOMER_RETURN_TO
    : (normalizeCustomerReturnTo(value) ?? DEFAULT_CUSTOMER_RETURN_TO);
}
