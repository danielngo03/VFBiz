import Joi from 'joi';
import { parseTrustedProxyCidrs } from './trusted-proxy.config';

export type RuntimeEnvironment =
  'development' | 'test' | 'staging' | 'production';

export interface EnvironmentVariables {
  readonly NODE_ENV: RuntimeEnvironment;
  readonly VFBIZ_API_HOST: string;
  readonly VFBIZ_API_PORT: number;
  readonly VFBIZ_API_DOCS_ENABLED: boolean;
  readonly VFBIZ_WORKFORCE_API_DOCS_ENABLED: boolean;
  readonly VFBIZ_API_TRUSTED_PROXY_CIDRS: string;
  readonly VFBIZ_DATABASE_URL: string;
  readonly VFBIZ_REDIS_URL: string;
  readonly VFBIZ_CUSTOMER_OIDC_ISSUER: string;
  readonly VFBIZ_CUSTOMER_OIDC_JWKS_URI: string;
  readonly VFBIZ_CUSTOMER_OIDC_AUDIENCE: string;
  readonly VFBIZ_CUSTOMER_OIDC_AUTHORIZED_PARTIES: string;
  readonly VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_ID?: string;
  readonly VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_SECRET?: string;
  readonly VFBIZ_WORKFORCE_OIDC_ISSUER: string;
  readonly VFBIZ_WORKFORCE_OIDC_JWKS_URI: string;
  readonly VFBIZ_WORKFORCE_OIDC_AUDIENCE: string;
  readonly VFBIZ_WORKFORCE_OIDC_AUTHORIZED_PARTIES: string;
  readonly VFBIZ_CONVERSATION_CONTENT_ACTIVE_KEY_ID?: string;
  readonly VFBIZ_CONVERSATION_CONTENT_KEYRING?: string;
  readonly VFBIZ_INTERNAL_AI_ENABLED: boolean;
  readonly VFBIZ_INTERNAL_AI_DISPATCH_ENABLED: boolean;
  readonly VFBIZ_CHAT_API_MODE:
    'disabled' | 'authenticated-staging' | 'public-release';
  readonly VFBIZ_CHAT_LIVE_CONTROL_ID?: string;
  readonly VFBIZ_CHAT_LIVE_CONTROL_AUTHORITY_SHA256?: string;
  readonly VFBIZ_CHAT_LIVE_CONTROL_GENERATION?: number;
  readonly VFBIZ_CHAT_LIVE_CONTROL_NOT_BEFORE?: string;
  readonly VFBIZ_CHAT_LIVE_CONTROL_EXPIRES_AT?: string;
  readonly VFBIZ_CHAT_LIVE_CONTROL_RELEASE_ENVELOPE_SHA256?: string;
  readonly VFBIZ_CHAT_LIVE_CONTROL_RELEASE_POINTER_REVISION?: number;
  readonly VFBIZ_INTERNAL_AI_BASE_URL?: string;
  readonly VFBIZ_INTERNAL_AI_ALLOWED_HOSTS?: string;
  readonly VFBIZ_INTERNAL_AI_REQUEST_TIMEOUT_MS: number;
  readonly VFBIZ_INTERNAL_AI_RETRY_BUDGET: number;
  readonly VFBIZ_INTERNAL_AI_ASSERTION_ISSUER: 'vfbiz-api';
  readonly VFBIZ_INTERNAL_AI_ASSERTION_AUDIENCE: 'vfbiz-ai';
  readonly VFBIZ_INTERNAL_AI_ASSERTION_TTL_SECONDS: number;
  readonly VFBIZ_INTERNAL_AI_ASSERTION_ACTIVE_KEY_ID?: string;
  readonly VFBIZ_INTERNAL_AI_ASSERTION_KEYRING?: string;
  readonly VFBIZ_INTERNAL_AI_RESPONSE_VERIFICATION_KEYRING?: string;
  readonly VFBIZ_INTERNAL_AI_SUBJECT_PSEUDONYMIZATION_KEY?: string;
  readonly VFBIZ_LOG_LEVEL: string;
}

const keyIdSchema = Joi.string()
  .trim()
  .pattern(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/)
  .empty('');

const utcSecondTimestampSchema = Joi.string()
  .pattern(
    /^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\dZ$/,
  )
  .custom((value: string, helpers) => {
    const parsed = new Date(value);
    if (
      !Number.isFinite(parsed.getTime()) ||
      parsed.toISOString().replace('.000Z', 'Z') !== value
    ) {
      return helpers.error('any.invalid');
    }
    return value;
  });

const environmentSchema = Joi.object<EnvironmentVariables>({
  NODE_ENV: Joi.string()
    .valid('development', 'test', 'staging', 'production')
    .default('development'),
  VFBIZ_API_HOST: Joi.string().hostname().default('127.0.0.1'),
  VFBIZ_API_PORT: Joi.number().port().default(8000),
  VFBIZ_API_DOCS_ENABLED: Joi.boolean()
    .truthy('true')
    .falsy('false')
    .when('NODE_ENV', {
      is: 'development',
      then: Joi.boolean().default(true),
      otherwise: Joi.boolean().default(false),
    }),
  VFBIZ_WORKFORCE_API_DOCS_ENABLED: Joi.boolean()
    .truthy('true')
    .falsy('false')
    .when('NODE_ENV', {
      is: 'development',
      then: Joi.boolean().default(true),
      otherwise: Joi.boolean().default(false),
    }),
  VFBIZ_API_TRUSTED_PROXY_CIDRS: Joi.string()
    .trim()
    .allow('')
    .max(4_096)
    .default(''),
  VFBIZ_DATABASE_URL: Joi.string()
    .uri({ scheme: ['postgresql'] })
    .required(),
  VFBIZ_REDIS_URL: Joi.string()
    .uri({ scheme: ['redis', 'rediss'] })
    .required(),
  VFBIZ_CUSTOMER_OIDC_ISSUER: Joi.string()
    .uri({ scheme: ['http', 'https'] })
    .required(),
  VFBIZ_CUSTOMER_OIDC_JWKS_URI: Joi.string()
    .uri({ scheme: ['http', 'https'] })
    .required(),
  VFBIZ_CUSTOMER_OIDC_AUDIENCE: Joi.string().trim().min(1).required(),
  VFBIZ_CUSTOMER_OIDC_AUTHORIZED_PARTIES: Joi.string()
    .trim()
    .pattern(/^[A-Za-z0-9._:-]+(?:,[A-Za-z0-9._:-]+)*$/)
    .required(),
  VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_ID: Joi.string().trim().empty('').optional(),
  VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_SECRET: Joi.string()
    .trim()
    .empty('')
    .optional(),
  VFBIZ_WORKFORCE_OIDC_ISSUER: Joi.string()
    .uri({ scheme: ['http', 'https'] })
    .required(),
  VFBIZ_WORKFORCE_OIDC_JWKS_URI: Joi.string()
    .uri({ scheme: ['http', 'https'] })
    .required(),
  VFBIZ_WORKFORCE_OIDC_AUDIENCE: Joi.string().trim().min(1).required(),
  VFBIZ_WORKFORCE_OIDC_AUTHORIZED_PARTIES: Joi.string()
    .trim()
    .pattern(/^[A-Za-z0-9._:-]+(?:,[A-Za-z0-9._:-]+)*$/)
    .required(),
  VFBIZ_CONVERSATION_CONTENT_ACTIVE_KEY_ID: keyIdSchema.optional(),
  VFBIZ_CONVERSATION_CONTENT_KEYRING: Joi.string().trim().empty('').optional(),
  VFBIZ_INTERNAL_AI_ENABLED: Joi.boolean()
    .truthy('true')
    .falsy('false')
    .default(false),
  VFBIZ_INTERNAL_AI_DISPATCH_ENABLED: Joi.boolean()
    .truthy('true')
    .falsy('false')
    .default(false),
  VFBIZ_CHAT_API_MODE: Joi.string()
    .valid('disabled', 'authenticated-staging', 'public-release')
    .default('disabled'),
  VFBIZ_CHAT_LIVE_CONTROL_ID: Joi.string()
    .pattern(/^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/)
    .optional(),
  VFBIZ_CHAT_LIVE_CONTROL_AUTHORITY_SHA256: Joi.string()
    .pattern(/^[a-f0-9]{64}$/)
    .optional(),
  VFBIZ_CHAT_LIVE_CONTROL_GENERATION: Joi.number()
    .integer()
    .positive()
    .max(Number.MAX_SAFE_INTEGER)
    .unsafe(false)
    .optional(),
  VFBIZ_CHAT_LIVE_CONTROL_NOT_BEFORE: utcSecondTimestampSchema.optional(),
  VFBIZ_CHAT_LIVE_CONTROL_EXPIRES_AT: utcSecondTimestampSchema.optional(),
  VFBIZ_CHAT_LIVE_CONTROL_RELEASE_ENVELOPE_SHA256: Joi.string()
    .pattern(/^[a-f0-9]{64}$/)
    .optional(),
  VFBIZ_CHAT_LIVE_CONTROL_RELEASE_POINTER_REVISION: Joi.number()
    .integer()
    .positive()
    .max(Number.MAX_SAFE_INTEGER)
    .unsafe(false)
    .optional(),
  VFBIZ_INTERNAL_AI_BASE_URL: Joi.string()
    .uri({ scheme: ['http', 'https'] })
    .empty('')
    .optional(),
  VFBIZ_INTERNAL_AI_ALLOWED_HOSTS: Joi.string()
    .trim()
    .pattern(
      /^(?:localhost|[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?|\[[0-9A-Fa-f:]+\])(?:,(?:localhost|[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?|\[[0-9A-Fa-f:]+\]))*$/,
    )
    .empty('')
    .optional(),
  VFBIZ_INTERNAL_AI_REQUEST_TIMEOUT_MS: Joi.number()
    .integer()
    .min(100)
    .max(60_000)
    .default(15_000),
  VFBIZ_INTERNAL_AI_RETRY_BUDGET: Joi.number()
    .integer()
    .min(0)
    .max(2)
    .default(1),
  VFBIZ_INTERNAL_AI_ASSERTION_ISSUER: Joi.string()
    .valid('vfbiz-api')
    .default('vfbiz-api'),
  VFBIZ_INTERNAL_AI_ASSERTION_AUDIENCE: Joi.string()
    .valid('vfbiz-ai')
    .default('vfbiz-ai'),
  VFBIZ_INTERNAL_AI_ASSERTION_TTL_SECONDS: Joi.number()
    .integer()
    .min(5)
    .max(60)
    .default(30),
  VFBIZ_INTERNAL_AI_ASSERTION_ACTIVE_KEY_ID: keyIdSchema.optional(),
  VFBIZ_INTERNAL_AI_ASSERTION_KEYRING: Joi.string()
    .trim()
    .max(32_768)
    .empty('')
    .optional(),
  VFBIZ_INTERNAL_AI_RESPONSE_VERIFICATION_KEYRING: Joi.string()
    .trim()
    .max(32_768)
    .empty('')
    .optional(),
  VFBIZ_INTERNAL_AI_SUBJECT_PSEUDONYMIZATION_KEY: Joi.string()
    .base64()
    .min(44)
    .max(256)
    .empty('')
    .optional(),
  VFBIZ_LOG_LEVEL: Joi.string()
    .valid('fatal', 'error', 'warn', 'info', 'debug', 'trace', 'silent')
    .default('info'),
}).unknown(true);

export function validateEnvironment(
  input: Record<string, unknown>,
): EnvironmentVariables {
  const validation: Joi.ValidationResult<EnvironmentVariables> =
    environmentSchema.validate(input, {
      abortEarly: false,
      convert: true,
    });
  const error = validation.error;
  if (error) throw new Error(`Invalid API environment: ${error.message}`);

  const validated: EnvironmentVariables = validation.value;
  try {
    parseTrustedProxyCidrs(validated.VFBIZ_API_TRUSTED_PROXY_CIDRS);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'invalid value';
    throw new Error(
      `Invalid API environment: VFBIZ_API_TRUSTED_PROXY_CIDRS ${message}`,
    );
  }
  if (
    validated.VFBIZ_CUSTOMER_OIDC_ISSUER ===
    validated.VFBIZ_WORKFORCE_OIDC_ISSUER
  ) {
    throw new Error(
      'Invalid API environment: customer and workforce OIDC issuers must be distinct',
    );
  }
  const hasCiamAdminClient =
    validated.VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_ID !== undefined;
  const hasCiamAdminSecret =
    validated.VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_SECRET !== undefined;
  if (hasCiamAdminClient !== hasCiamAdminSecret) {
    throw new Error(
      'Invalid API environment: customer CIAM admin client id and secret must be configured together',
    );
  }
  const hasConversationContentActiveKey =
    validated.VFBIZ_CONVERSATION_CONTENT_ACTIVE_KEY_ID !== undefined;
  const hasConversationContentKeyring =
    validated.VFBIZ_CONVERSATION_CONTENT_KEYRING !== undefined;
  if (hasConversationContentActiveKey !== hasConversationContentKeyring) {
    throw new Error(
      'Invalid API environment: conversation content active key id and keyring must be configured together',
    );
  }
  const internalAiRequiredValues = [
    validated.VFBIZ_INTERNAL_AI_BASE_URL,
    validated.VFBIZ_INTERNAL_AI_ALLOWED_HOSTS,
    validated.VFBIZ_INTERNAL_AI_ASSERTION_ACTIVE_KEY_ID,
    validated.VFBIZ_INTERNAL_AI_ASSERTION_KEYRING,
    validated.VFBIZ_INTERNAL_AI_RESPONSE_VERIFICATION_KEYRING,
    validated.VFBIZ_INTERNAL_AI_SUBJECT_PSEUDONYMIZATION_KEY,
  ];
  if (
    validated.VFBIZ_INTERNAL_AI_ENABLED &&
    internalAiRequiredValues.some((value) => value === undefined)
  ) {
    throw new Error(
      'Invalid API environment: enabled internal AI requires base URL, exact host allowlist, assertion keyring, response verification keyring and subject pseudonymization key',
    );
  }
  if (
    validated.VFBIZ_INTERNAL_AI_DISPATCH_ENABLED &&
    !validated.VFBIZ_INTERNAL_AI_ENABLED
  ) {
    throw new Error(
      'Invalid API environment: internal AI dispatch requires internal AI trust to be enabled',
    );
  }
  const liveControlValues = [
    validated.VFBIZ_CHAT_LIVE_CONTROL_ID,
    validated.VFBIZ_CHAT_LIVE_CONTROL_AUTHORITY_SHA256,
    validated.VFBIZ_CHAT_LIVE_CONTROL_GENERATION,
    validated.VFBIZ_CHAT_LIVE_CONTROL_NOT_BEFORE,
    validated.VFBIZ_CHAT_LIVE_CONTROL_EXPIRES_AT,
    validated.VFBIZ_CHAT_LIVE_CONTROL_RELEASE_ENVELOPE_SHA256,
    validated.VFBIZ_CHAT_LIVE_CONTROL_RELEASE_POINTER_REVISION,
  ];
  if (validated.VFBIZ_CHAT_API_MODE === 'authenticated-staging') {
    if (!['staging', 'test'].includes(validated.NODE_ENV)) {
      throw new Error(
        'Invalid API environment: authenticated staging Chat is permitted only in staging/test',
      );
    }
    if (
      !validated.VFBIZ_INTERNAL_AI_ENABLED ||
      !validated.VFBIZ_INTERNAL_AI_DISPATCH_ENABLED
    ) {
      throw new Error(
        'Invalid API environment: authenticated staging Chat requires enabled internal AI dispatch',
      );
    }
    if (liveControlValues.some((value) => value === undefined)) {
      throw new Error(
        'Invalid API environment: authenticated staging Chat requires complete live-control identity, authority, generation, validity window and release anchor',
      );
    }
    const notBefore = Date.parse(
      validated.VFBIZ_CHAT_LIVE_CONTROL_NOT_BEFORE as string,
    );
    const expiresAt = Date.parse(
      validated.VFBIZ_CHAT_LIVE_CONTROL_EXPIRES_AT as string,
    );
    if (notBefore >= expiresAt) {
      throw new Error(
        'Invalid API environment: authenticated staging Chat live-control not-before must precede expires-at',
      );
    }
    if (expiresAt - notBefore > 24 * 60 * 60 * 1_000) {
      throw new Error(
        'Invalid API environment: authenticated staging Chat live-control validity window must not exceed 24 hours',
      );
    }
  } else if (liveControlValues.some((value) => value !== undefined)) {
    throw new Error(
      'Invalid API environment: live-control values require authenticated staging Chat mode',
    );
  }
  if (validated.VFBIZ_CHAT_API_MODE === 'public-release') {
    throw new Error(
      'Invalid API environment: public Chat release is not available before VFBIZ-0195',
    );
  }
  if (
    !validated.VFBIZ_INTERNAL_AI_ENABLED &&
    internalAiRequiredValues.some((value) => value !== undefined)
  ) {
    throw new Error(
      'Invalid API environment: internal AI trust values require VFBIZ_INTERNAL_AI_ENABLED=true',
    );
  }
  if (
    validated.VFBIZ_INTERNAL_AI_ENABLED &&
    validated.VFBIZ_INTERNAL_AI_BASE_URL !== undefined &&
    validated.VFBIZ_INTERNAL_AI_ALLOWED_HOSTS !== undefined
  ) {
    validateInternalAiOrigin(
      validated.VFBIZ_INTERNAL_AI_BASE_URL,
      validated.VFBIZ_INTERNAL_AI_ALLOWED_HOSTS,
      validated.NODE_ENV,
    );
  }
  if (
    validated.VFBIZ_CUSTOMER_OIDC_AUDIENCE ===
    validated.VFBIZ_WORKFORCE_OIDC_AUDIENCE
  ) {
    throw new Error(
      'Invalid API environment: customer and workforce OIDC audiences must be distinct',
    );
  }
  if (validated.NODE_ENV === 'production') {
    if (validated.VFBIZ_WORKFORCE_API_DOCS_ENABLED) {
      throw new Error(
        'Invalid API environment: workforce API documentation must be disabled in production',
      );
    }
    const oidcUris = [
      validated.VFBIZ_CUSTOMER_OIDC_ISSUER,
      validated.VFBIZ_CUSTOMER_OIDC_JWKS_URI,
      validated.VFBIZ_WORKFORCE_OIDC_ISSUER,
      validated.VFBIZ_WORKFORCE_OIDC_JWKS_URI,
    ];
    if (oidcUris.some((value) => new URL(value).protocol !== 'https:')) {
      throw new Error(
        'Invalid API environment: OIDC issuer and JWKS URIs must use HTTPS in production',
      );
    }
  }
  return Object.freeze(validated);
}

function validateInternalAiOrigin(
  rawBaseUrl: string,
  rawAllowedHosts: string,
  environment: RuntimeEnvironment,
): void {
  const baseUrl = new URL(rawBaseUrl);
  if (
    baseUrl.username ||
    baseUrl.password ||
    baseUrl.search ||
    baseUrl.hash ||
    (baseUrl.pathname !== '' && baseUrl.pathname !== '/')
  ) {
    throw new Error(
      'Invalid API environment: internal AI base URL must be an origin without credentials, path, query or fragment',
    );
  }
  const hostname = normalizedHostname(baseUrl.hostname);
  const allowedHosts = new Set(
    rawAllowedHosts.split(',').map(normalizedHostname),
  );
  if (!allowedHosts.has(hostname)) {
    throw new Error(
      'Invalid API environment: internal AI base URL host is not in the exact allowlist',
    );
  }
  if (
    (environment === 'staging' || environment === 'production') &&
    baseUrl.protocol !== 'https:'
  ) {
    throw new Error(
      'Invalid API environment: internal AI base URL must use HTTPS in staging and production',
    );
  }
  if (
    (environment === 'staging' || environment === 'production') &&
    (hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1')
  ) {
    throw new Error(
      'Invalid API environment: loopback internal AI host is forbidden in staging and production',
    );
  }
}

function normalizedHostname(value: string): string {
  return value
    .trim()
    .replace(/^\[|\]$/g, '')
    .toLowerCase();
}
