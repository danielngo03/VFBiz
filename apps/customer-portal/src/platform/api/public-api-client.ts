import "server-only";

import type { paths } from "@vfbiz/api-client";
import createClient from "openapi-fetch";

function publicApiFetch(input: RequestInfo | URL, init?: RequestInit) {
  return fetch(input, {
    ...init,
    cache: "no-store",
    credentials: "omit",
    redirect: "error",
    signal: init?.signal ?? AbortSignal.timeout(10_000),
  });
}

export function createPublicApiClient(baseUrl: string) {
  return createClient<paths>({
    baseUrl,
    fetch: publicApiFetch,
  });
}
