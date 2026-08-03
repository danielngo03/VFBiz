const sensitiveKeys = new Set([
  "accesstoken",
  "access_token",
  "refreshtoken",
  "refresh_token",
  "idtoken",
  "id_token",
  "authorization",
  "email",
  "vin",
  "displayname",
  "customerid",
  "customer_id",
  "query",
]);

export function scrubTelemetry(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(scrubTelemetry);
  if (typeof value !== "object" || value === null) return value;
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, item]) => [
      key,
      sensitiveKeys.has(key.toLowerCase()) ? "[REDACTED]" : scrubTelemetry(item),
    ]),
  );
}

export function recordHandledError(
  error: unknown,
  context: Record<string, unknown> = {},
): void {
  if (__DEV__)
    console.warn("customer-mobile-handled-error", {
      errorName: error instanceof Error ? error.name : "UnknownError",
      context: scrubTelemetry(context),
    });
}
