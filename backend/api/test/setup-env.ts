const defaults: Readonly<Record<string, string>> = {
  NODE_ENV: 'test',
  VFBIZ_API_DOCS_ENABLED: 'true',
  VFBIZ_WORKFORCE_API_DOCS_ENABLED: 'true',
  VFBIZ_DATABASE_URL:
    'postgresql://vfbiz_test:vfbiz_test@127.0.0.1:5432/vfbiz_test',
  VFBIZ_REDIS_URL: 'redis://127.0.0.1:6379/15',
  VFBIZ_CUSTOMER_OIDC_ISSUER: 'http://127.0.0.1:8080/realms/vfbiz-customer',
  VFBIZ_CUSTOMER_OIDC_JWKS_URI:
    'http://127.0.0.1:8080/realms/vfbiz-customer/protocol/openid-connect/certs',
  VFBIZ_CUSTOMER_OIDC_AUDIENCE: 'vfbiz-customer-api',
  VFBIZ_CUSTOMER_OIDC_AUTHORIZED_PARTIES: 'vfbiz-customer-bff,vfbiz-mobile',
  VFBIZ_WORKFORCE_OIDC_ISSUER: 'http://127.0.0.1:8080/realms/vfbiz-workforce',
  VFBIZ_WORKFORCE_OIDC_JWKS_URI:
    'http://127.0.0.1:8080/realms/vfbiz-workforce/protocol/openid-connect/certs',
  VFBIZ_WORKFORCE_OIDC_AUDIENCE: 'vfbiz-workforce-api',
  VFBIZ_WORKFORCE_OIDC_AUTHORIZED_PARTIES: 'vfbiz-workforce-bff',
};

for (const [name, value] of Object.entries(defaults)) {
  process.env[name] ??= value;
}
