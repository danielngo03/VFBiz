import "server-only";
import { z } from "zod";

const schema = z.object({
  CUSTOMER_API_BASE_URL: z.string().url(),
  CUSTOMER_OIDC_ISSUER: z.string().url(),
  CUSTOMER_OIDC_CLIENT_ID: z.string().min(1),
  CUSTOMER_OIDC_CLIENT_SECRET: z.string().min(16),
  CUSTOMER_OIDC_REDIRECT_URI: z.string().url(),
  CUSTOMER_REDIS_URL: z.string().url(),
  CUSTOMER_PROVIDER_RECONCILIATION_TOKEN: z.string().min(32).optional(),
  CUSTOMER_TOKEN_VAULT_KEY: z
    .string()
    .refine(
      (value) => Buffer.from(value, "base64").byteLength === 32,
      "CUSTOMER_TOKEN_VAULT_KEY must be a base64-encoded 32-byte key.",
    ),
  CUSTOMER_SESSION_COOKIE_NAME: z
    .string()
    .min(1)
    .default("vfbiz_customer_session"),
  CUSTOMER_SESSION_COOKIE_SECURE: z
    .enum(["true", "false"])
    .default("false")
    .transform((value) => value === "true"),
  CUSTOMER_SESSION_MAX_AGE_SECONDS: z.coerce
    .number()
    .int()
    .min(900)
    .max(30 * 24 * 60 * 60)
    .default(14 * 24 * 60 * 60),
  CUSTOMER_SESSION_IDLE_TIMEOUT_SECONDS: z.coerce
    .number()
    .int()
    .min(300)
    .max(7 * 24 * 60 * 60)
    .default(24 * 60 * 60),
  CUSTOMER_TRUST_PROXY_HEADERS: z
    .enum(["true", "false"])
    .default("false")
    .transform((value) => value === "true"),
});

export function readCustomerPortalEnvironment(
  source: NodeJS.ProcessEnv = process.env,
) {
  return schema.parse(source);
}
