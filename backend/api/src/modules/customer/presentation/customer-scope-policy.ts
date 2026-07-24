export const CUSTOMER_AUTHORIZED_PARTIES = [
  'vfbiz-customer-bff',
  'vfbiz-mobile',
] as const;

export const CUSTOMER_OPERATION_SCOPES = Object.freeze({
  consentRead: 'consent:read',
  consentWrite: 'consent:write',
  dataRequestCreate: 'data-request:create',
  dataRequestRead: 'data-request:read',
  garageRead: 'garage:read',
  garageWrite: 'garage:write',
  profileRead: 'profile:read',
  profileWrite: 'profile:write',
} as const);
