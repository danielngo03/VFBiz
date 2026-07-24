import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import {
  CustomerAccountRepository,
  type CreateCustomerDataRequestInput,
  type RecordConsentInput,
  type UpdateCustomerProfileInput,
} from '../ports/customer-account.repository';
import type {
  CurrentConsentView,
  CustomerDataRequestView,
  CustomerProfileView,
} from '../../domain/customer-account';
import { CustomerConsentBatchValidationError } from '../../domain/customer-account';
import { CustomerAccountService } from './customer-account.service';

const customerPrincipal = (
  authorizedParty = 'vfbiz-customer-bff',
): AccessPrincipal => ({
  authenticationContext: 'urn:vfbiz:loa:1',
  authenticationMethods: ['pwd'],
  audience: ['vfbiz-customer-api'],
  authorizedParty,
  issuer: 'https://id.example/realms/customer',
  realm: 'customer',
  scopes: ['profile:read', 'profile:write'],
  sessionId: 'session-123',
  subject: 'customer-123',
});

const profile: CustomerProfileView = {
  communicationPreferences: { email: false, push: false, sms: false },
  displayName: null,
  locale: 'vi',
  market: 'VN',
  timezone: 'Asia/Ho_Chi_Minh',
  updatedAt: new Date('2026-07-23T07:00:00.000Z'),
  version: 1,
};

class StubCustomerAccountRepository extends CustomerAccountRepository {
  readonly updateProfile = jest.fn<
    Promise<CustomerProfileView>,
    [UpdateCustomerProfileInput]
  >(() => Promise.resolve(profile));
  readonly recordConsents = jest.fn<
    Promise<readonly CurrentConsentView[]>,
    [readonly RecordConsentInput[]]
  >(() => Promise.resolve([]));
  readonly createDataRequest = jest.fn<
    Promise<CustomerDataRequestView>,
    [CreateCustomerDataRequestInput]
  >(() =>
    Promise.resolve({
      completedAt: null,
      id: '57e9aa3e-9572-4021-86af-f8c05ad8ab23',
      requestedAt: new Date('2026-07-23T07:00:00.000Z'),
      status: 'requested',
      type: 'export',
    }),
  );

  provisionProfile(): Promise<CustomerProfileView> {
    return Promise.resolve(profile);
  }

  listCurrentConsents(): Promise<readonly CurrentConsentView[]> {
    return Promise.resolve([]);
  }

  listDataRequests(): Promise<readonly CustomerDataRequestView[]> {
    return Promise.resolve([]);
  }

  getDataRequest(): Promise<CustomerDataRequestView> {
    return Promise.resolve({
      completedAt: null,
      id: '57e9aa3e-9572-4021-86af-f8c05ad8ab23',
      requestedAt: new Date('2026-07-23T07:00:00.000Z'),
      status: 'requested',
      type: 'export',
    });
  }
}

describe('CustomerAccountService contract (mock repository)', () => {
  it('passes optimistic version and typed profile patch to the repository', async () => {
    const repository = new StubCustomerAccountRepository();
    const service = new CustomerAccountService(repository);

    await service.updateProfile(
      customerPrincipal(),
      '11111111-1111-4111-a111-111111111111',
      4,
      {
        displayName: 'Anh Tuấn',
        communicationPreferences: { email: true },
      },
    );

    expect(repository.updateProfile).toHaveBeenCalledWith({
      correlationId: '11111111-1111-4111-a111-111111111111',
      displayName: 'Anh Tuấn',
      expectedVersion: 4,
      communicationPreferences: { email: true },
      principal: customerPrincipal(),
    });
  });

  it('derives consent source and stable per-purpose correlation IDs', async () => {
    const repository = new StubCustomerAccountRepository();
    const service = new CustomerAccountService(repository);
    const idempotencyKey = 'consent-request-0001';
    const commands = [
      {
        policyVersion: 'marketing-2026-07',
        purpose: 'marketing_email' as const,
        state: 'granted' as const,
      },
      {
        policyVersion: 'analytics-2026-07',
        purpose: 'analytics' as const,
        state: 'withdrawn' as const,
      },
    ];

    await service.recordConsents(
      customerPrincipal('vfbiz-mobile'),
      idempotencyKey,
      commands,
    );
    const firstCall = repository.recordConsents.mock.calls[0][0];
    await service.recordConsents(
      customerPrincipal('vfbiz-mobile'),
      idempotencyKey,
      commands,
    );
    const secondCall = repository.recordConsents.mock.calls[1][0];

    expect(firstCall.map((event) => event.source)).toEqual([
      'mobile',
      'mobile',
    ]);
    expect(firstCall.map((event) => event.idempotencyKey)).toEqual([
      idempotencyKey,
      idempotencyKey,
    ]);
    expect(firstCall[0].correlationId).not.toBe(firstCall[1].correlationId);
    expect(firstCall.map((event) => event.correlationId)).toEqual(
      secondCall.map((event) => event.correlationId),
    );
  });

  it('rejects duplicate consent purposes before persistence', () => {
    const repository = new StubCustomerAccountRepository();
    const service = new CustomerAccountService(repository);

    expect(() =>
      service.recordConsents(customerPrincipal(), 'consent-request-0002', [
        {
          policyVersion: 'analytics-2026-07',
          purpose: 'analytics',
          state: 'granted',
        },
        {
          policyVersion: 'analytics-2026-08',
          purpose: 'analytics',
          state: 'withdrawn',
        },
      ]),
    ).toThrow(CustomerConsentBatchValidationError);
    expect(repository.recordConsents).not.toHaveBeenCalled();
  });

  it('passes idempotency and a server-derived source to DSAR creation', async () => {
    const repository = new StubCustomerAccountRepository();
    const service = new CustomerAccountService(repository);

    await service.createDataRequest(
      customerPrincipal(),
      'b6685412-5a33-42e6-9eb4-eb2071c863d0',
      'customer-request-0001',
      'export',
    );

    expect(repository.createDataRequest).toHaveBeenCalledWith({
      correlationId: 'b6685412-5a33-42e6-9eb4-eb2071c863d0',
      idempotencyKey: 'customer-request-0001',
      principal: customerPrincipal(),
      source: 'customer_portal',
      type: 'export',
    });
  });
});
