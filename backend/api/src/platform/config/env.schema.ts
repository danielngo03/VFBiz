import Joi from 'joi';

export type RuntimeEnvironment =
  'development' | 'test' | 'staging' | 'production';

export interface EnvironmentVariables {
  readonly NODE_ENV: RuntimeEnvironment;
  readonly VFBIZ_API_HOST: string;
  readonly VFBIZ_API_PORT: number;
  readonly VFBIZ_API_DOCS_ENABLED: boolean;
  readonly VFBIZ_WORKFORCE_API_DOCS_ENABLED: boolean;
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
  readonly VFBIZ_LOG_LEVEL: string;
}

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
