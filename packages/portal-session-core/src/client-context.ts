import "server-only";
import type { ClientContext } from "./contracts";

const MAX_LABEL_LENGTH = 120;

function clean(value: string | null, limit = MAX_LABEL_LENGTH): string | null {
  if (value === null) return null;
  const normalized = value.replace(/[\u0000-\u001f\u007f]+/gu, " ").trim();
  return normalized.length === 0 ? null : normalized.slice(0, limit);
}

export function deriveClientContext(request: Request): ClientContext {
  const userAgent = clean(request.headers.get("user-agent"), 240);
  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0] ?? null;
  return {
    deviceLabel: userAgent,
    networkHint: clean(forwarded, 64),
    userAgentSummary: userAgent,
  };
}
