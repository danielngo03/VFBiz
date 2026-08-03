import { runtimeConfig } from "../config/runtime-config";
import { ApiProblemError, problemFromResponse } from "./problem";
import * as Crypto from "expo-crypto";

export interface ApiRequestOptions extends Omit<RequestInit, "headers"> {
  accessToken: string;
  headers?: Record<string, string>;
  idempotencyKey?: string;
  ifMatch?: string;
}

export async function apiRequest<T>(
  path: `/api/v1/${string}`,
  options: ApiRequestOptions,
): Promise<{ data: T; etag?: string; correlationId?: string }> {
  const correlationId = Crypto.randomUUID();
  const response = await fetch(`${runtimeConfig.apiBaseUrl}${path}`, {
    ...options,
    headers: {
      accept: "application/json",
      authorization: `Bearer ${options.accessToken}`,
      "x-correlation-id": correlationId,
      ...(options.body ? { "content-type": "application/json" } : {}),
      ...(options.idempotencyKey
        ? { "idempotency-key": options.idempotencyKey }
        : {}),
      ...(options.ifMatch ? { "if-match": options.ifMatch } : {}),
      ...options.headers,
    },
  });
  const responseCorrelationId = response.headers.get("x-correlation-id") ?? undefined;
  const body = await response.json().catch(() => undefined);
  if (!response.ok)
    throw new ApiProblemError(
      problemFromResponse(response.status, body, responseCorrelationId),
    );
  const etag = response.headers.get("etag") ?? undefined;
  return {
    data: body as T,
    ...(etag ? { etag } : {}),
    ...(responseCorrelationId ? { correlationId: responseCorrelationId } : {}),
  };
}
