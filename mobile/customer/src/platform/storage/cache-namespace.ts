import type { CustomerEnvironment } from "../config/runtime-config";

export const CACHE_SCHEMA_VERSION = 1;

export interface CacheNamespaceInput {
  app: "customer";
  environment: CustomerEnvironment;
  issuer: string;
  subject: string;
  market: string;
  schemaVersion?: number;
}

export function cacheNamespace(input: CacheNamespaceInput): string {
  const required = [input.issuer, input.subject, input.market];
  if (required.some((value) => value.trim() === ""))
    throw new Error("Cache namespace fields must not be empty.");
  return [
    input.app,
    input.environment,
    encodeURIComponent(input.issuer),
    encodeURIComponent(input.subject),
    input.market.toUpperCase(),
    input.schemaVersion ?? CACHE_SCHEMA_VERSION,
  ].join(":");
}
