import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import type {
  CommunicationPreferences,
  ConsentPurpose,
  ConsentState,
  CurrentConsentView,
  CustomerDataRequestType,
  CustomerDataRequestView,
  CustomerLocale,
  CustomerMarket,
  CustomerProfileView,
  CustomerRequestSource,
} from '../../domain/customer-account';

export interface UpdateCustomerProfileInput {
  readonly correlationId: string;
  readonly displayName?: string | null;
  readonly expectedVersion: number;
  readonly locale?: CustomerLocale;
  readonly market?: CustomerMarket;
  readonly communicationPreferences?: Partial<CommunicationPreferences>;
  readonly principal: AccessPrincipal;
  readonly timezone?: string;
}

export interface RecordConsentInput {
  readonly correlationId: string;
  readonly idempotencyKey: string;
  readonly policyVersion: string;
  readonly principal: AccessPrincipal;
  readonly purpose: ConsentPurpose;
  readonly source: CustomerRequestSource;
  readonly state: ConsentState;
}

export interface CreateCustomerDataRequestInput {
  readonly correlationId: string;
  readonly idempotencyKey: string;
  readonly principal: AccessPrincipal;
  readonly source: CustomerRequestSource;
  readonly type: CustomerDataRequestType;
}

export abstract class CustomerAccountRepository {
  abstract provisionProfile(
    principal: AccessPrincipal,
  ): Promise<CustomerProfileView>;

  abstract updateProfile(
    input: UpdateCustomerProfileInput,
  ): Promise<CustomerProfileView>;

  abstract listCurrentConsents(
    principal: AccessPrincipal,
  ): Promise<readonly CurrentConsentView[]>;

  abstract recordConsents(
    input: readonly RecordConsentInput[],
  ): Promise<readonly CurrentConsentView[]>;

  abstract createDataRequest(
    input: CreateCustomerDataRequestInput,
  ): Promise<CustomerDataRequestView>;

  abstract listDataRequests(
    principal: AccessPrincipal,
  ): Promise<readonly CustomerDataRequestView[]>;

  abstract getDataRequest(
    principal: AccessPrincipal,
    requestId: string,
  ): Promise<CustomerDataRequestView>;
}
