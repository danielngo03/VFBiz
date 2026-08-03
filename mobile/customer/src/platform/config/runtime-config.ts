import Constants from "expo-constants";

export type CustomerEnvironment = "development" | "preview" | "production";

export interface CustomerRuntimeConfig {
  environment: CustomerEnvironment;
  apiBaseUrl: string;
  oidcIssuer: string;
  oidcClientId: string;
  redirectScheme: string;
  market: string;
  assistantEnabled: boolean;
}

type PublicExtra = Record<string, unknown>;

function requiredString(extra: PublicExtra, key: string): string {
  const value = extra[key];
  if (typeof value !== "string" || value.trim() === "")
    throw new Error(`Missing public runtime config: ${key}`);
  return value;
}

function validatedUrl(value: string, production: boolean, key: string): string {
  const parsed = new URL(value);
  if (production && parsed.protocol !== "https:")
    throw new Error(`${key} must use HTTPS in production.`);
  if (!production && !["http:", "https:"].includes(parsed.protocol))
    throw new Error(`${key} must use HTTP or HTTPS.`);
  return parsed.toString().replace(/\/$/u, "");
}

export function runtimeConfigFromExtra(extra: PublicExtra): CustomerRuntimeConfig {
  const environment = requiredString(extra, "customerEnvironment");
  if (!["development", "preview", "production"].includes(environment))
    throw new Error(`Unsupported customer environment: ${environment}`);
  const secureEnvironment = environment !== "development";
  return {
    environment: environment as CustomerEnvironment,
    apiBaseUrl: validatedUrl(
      requiredString(extra, "apiBaseUrl"),
      secureEnvironment,
      "apiBaseUrl",
    ),
    oidcIssuer: validatedUrl(
      requiredString(extra, "oidcIssuer"),
      secureEnvironment,
      "oidcIssuer",
    ),
    oidcClientId: requiredString(extra, "oidcClientId"),
    redirectScheme: requiredString(extra, "redirectScheme"),
    market: requiredString(extra, "market").toUpperCase(),
    assistantEnabled: extra.assistantEnabled === true,
  };
}

export const runtimeConfig = runtimeConfigFromExtra(
  (Constants.expoConfig?.extra ?? {}) as PublicExtra,
);
