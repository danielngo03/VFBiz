export const CUSTOMER_LOCALES = ['vi', 'en'] as const;
export type CustomerLocale = (typeof CUSTOMER_LOCALES)[number];

export const CUSTOMER_MARKETS = ['VN'] as const;
export type CustomerMarket = (typeof CUSTOMER_MARKETS)[number];

export const CONSENT_PURPOSES = [
  'analytics',
  'marketing_email',
  'marketing_sms',
  'marketing_push',
  'personalization',
] as const;
export type ConsentPurpose = (typeof CONSENT_PURPOSES)[number];

export type ConsentState = 'granted' | 'withdrawn';
export type CustomerDataRequestType = 'export' | 'delete';
export type CustomerRequestSource =
  'customer_portal' | 'mobile' | 'operations_admin' | 'system_import';

export interface CommunicationPreferences {
  readonly email: boolean;
  readonly push: boolean;
  readonly sms: boolean;
}

export interface CustomerProfileView {
  readonly communicationPreferences: CommunicationPreferences;
  readonly displayName: string | null;
  readonly locale: CustomerLocale;
  readonly market: CustomerMarket;
  readonly timezone: string;
  readonly updatedAt: Date;
  readonly version: number;
}

export interface CurrentConsentView {
  readonly occurredAt: Date;
  readonly policyVersion: string;
  readonly purpose: ConsentPurpose;
  readonly source: CustomerRequestSource;
  readonly state: ConsentState;
}

export interface CustomerDataRequestView {
  readonly completedAt: Date | null;
  readonly id: string;
  readonly requestedAt: Date;
  readonly status:
    | 'requested'
    | 'processing'
    | 'partially_completed'
    | 'completed'
    | 'rejected';
  readonly type: CustomerDataRequestType;
}

const DSAR_EXPORT_TARGETS_V2 = Object.freeze([
  { key: 'access-identity', phase: 1, version: 'v1' },
  { key: 'customer-core', phase: 2, version: 'v1' },
  { key: 'engagement-data', phase: 3, version: 'v1' },
  { key: 'mobility-data', phase: 3, version: 'v1' },
  { key: 'commerce-ownership-data', phase: 3, version: 'v1' },
  { key: 'ai-data', phase: 4, version: 'v1' },
  { key: 'object-storage-cache', phase: 5, version: 'v1' },
  { key: 'telemetry-backup', phase: 6, version: 'v1' },
] as const);

const DSAR_DELETE_TARGETS_V2 = Object.freeze([
  { key: 'customer-core', phase: 1, version: 'v1' },
  { key: 'engagement-data', phase: 2, version: 'v1' },
  { key: 'mobility-data', phase: 2, version: 'v1' },
  { key: 'commerce-ownership-data', phase: 2, version: 'v1' },
  { key: 'ai-data', phase: 3, version: 'v1' },
  { key: 'object-storage-cache', phase: 4, version: 'v1' },
  { key: 'telemetry-backup', phase: 5, version: 'v1' },
  // Preserve the authoritative subject mapping until dependent targets finish.
  { key: 'access-identity', phase: 6, version: 'v1' },
] as const);

export const DSAR_TARGET_SET_REVISION = 'dsar-targets-v2';

export function dsarTargetPlan(type: CustomerDataRequestType) {
  return type === 'delete' ? DSAR_DELETE_TARGETS_V2 : DSAR_EXPORT_TARGETS_V2;
}

export class CustomerProfileUnavailableError extends Error {
  constructor() {
    super('Customer profile is unavailable.');
    this.name = 'CustomerProfileUnavailableError';
  }
}

export class CustomerProfileVersionConflictError extends Error {
  constructor() {
    super('Customer profile version does not match.');
    this.name = 'CustomerProfileVersionConflictError';
  }
}

export class CustomerIdempotencyConflictError extends Error {
  constructor() {
    super('Idempotency key was reused for a different request.');
    this.name = 'CustomerIdempotencyConflictError';
  }
}

export class CustomerConsentBatchValidationError extends Error {
  constructor() {
    super('Consent batch contains duplicate or inconsistent entries.');
    this.name = 'CustomerConsentBatchValidationError';
  }
}

export class CustomerConsentPolicyUnavailableError extends Error {
  constructor() {
    super('The requested consent policy is not active.');
    this.name = 'CustomerConsentPolicyUnavailableError';
  }
}

export class CustomerDataRequestNotFoundError extends Error {
  constructor() {
    super('The customer data request was not found.');
    this.name = 'CustomerDataRequestNotFoundError';
  }
}
