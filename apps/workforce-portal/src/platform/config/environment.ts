import 'server-only';
import {z} from 'zod';

const environmentSchema = z.object({
  WORKFORCE_API_BASE_URL: z.string().url(),
  WORKFORCE_OIDC_ISSUER: z.string().url(),
  WORKFORCE_OIDC_CLIENT_ID: z.string().min(1),
  WORKFORCE_OIDC_CLIENT_SECRET: z.string().min(16),
  WORKFORCE_OIDC_REDIRECT_URI: z.string().url(),
  WORKFORCE_REDIS_URL: z.string().url(),
  WORKFORCE_TOKEN_VAULT_KEY: z
    .string()
    .refine(
      (value) => Buffer.from(value, 'base64').byteLength === 32,
      'WORKFORCE_TOKEN_VAULT_KEY must be a base64-encoded 32-byte key.',
    ),
  WORKFORCE_SESSION_COOKIE_NAME: z.string().min(1).default('vfbiz-workforce-session'),
  WORKFORCE_SESSION_MAX_AGE_SECONDS: z.coerce
    .number()
    .int()
    .min(900)
    .max(12 * 60 * 60)
    .default(8 * 60 * 60),
  WORKFORCE_SESSION_IDLE_TIMEOUT_SECONDS: z.coerce
    .number()
    .int()
    .min(300)
    .max(4 * 60 * 60)
    .default(30 * 60),
  WORKFORCE_TRUST_PROXY_HEADERS: z
    .enum(['true', 'false'])
    .default('false')
    .transform((value) => value === 'true'),
});

export type WorkforcePortalEnvironment = z.infer<typeof environmentSchema>;

export function readWorkforcePortalEnvironment(
  source: NodeJS.ProcessEnv = process.env,
): WorkforcePortalEnvironment {
  return environmentSchema.parse(source);
}
