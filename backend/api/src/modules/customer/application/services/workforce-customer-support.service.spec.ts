import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import {
  WorkforceCustomerAccessReasonError,
  WorkforceCustomerSearchValidationError,
} from '../../domain/workforce-customer-support';
import { WorkforceCustomerSupportService } from './workforce-customer-support.service';

const principal: AccessPrincipal = {
  authenticatedAt: new Date('2026-07-24T08:00:00Z'),
  authenticationContext: null,
  authenticationMethods: ['otp'],
  audience: ['vfbiz-workforce-api'],
  authorizedParty: 'vfbiz-workforce-bff',
  issuer: 'https://id.example/realms/workforce',
  realm: 'workforce',
  scopes: [],
  sessionId: 'workforce-session',
  subject: 'agent-1',
};

describe('WorkforceCustomerSupportService', () => {
  it('restricts search to markets granted for the capability', async () => {
    const search = jest.fn().mockResolvedValue([]);
    const service = new WorkforceCustomerSupportService(
      {
        getEntitlements: jest.fn().mockResolvedValue({
          capabilities: [
            {
              key: 'customer-support.customer.read',
              riskTier: 'sensitive',
              scopes: [{ ref: 'VN', type: 'market' }],
            },
          ],
          identitySubjectId: '00000000-0000-4000-a000-000000000001',
          revision: '1',
        }),
      },
      { search },
    );

    await service.search({
      correlationId: '00000000-0000-4000-a000-000000000002',
      limit: 20,
      principal,
      query: 'Nguyen',
      reason: 'Resolve customer support request',
    });

    expect(search).toHaveBeenCalledWith(
      expect.objectContaining({
        allowedMarkets: ['VN'],
        query: 'Nguyen',
      }),
    );
  });

  it('returns no accessible market when the grant has no global/market scope', async () => {
    const search = jest.fn().mockResolvedValue([]);
    const service = new WorkforceCustomerSupportService(
      {
        getEntitlements: jest.fn().mockResolvedValue({
          capabilities: [],
          identitySubjectId: '00000000-0000-4000-a000-000000000001',
          revision: '1',
        }),
      },
      { search },
    );

    await service.search({
      correlationId: '00000000-0000-4000-a000-000000000002',
      limit: 20,
      principal,
      query: 'Nguyen',
      reason: 'Resolve customer support request',
    });

    expect(search).toHaveBeenCalledWith(
      expect.objectContaining({ allowedMarkets: [] }),
    );
  });

  it('rejects broad search and missing business purpose before data access', async () => {
    const repository = { search: jest.fn() };
    const service = new WorkforceCustomerSupportService(
      { getEntitlements: jest.fn() },
      repository,
    );
    const base = {
      correlationId: '00000000-0000-4000-a000-000000000002',
      limit: 20,
      principal,
    };
    await expect(
      service.search({ ...base, query: 'a', reason: 'Valid support reason' }),
    ).rejects.toBeInstanceOf(WorkforceCustomerSearchValidationError);
    await expect(
      service.search({ ...base, query: 'Nguyen', reason: 'short' }),
    ).rejects.toBeInstanceOf(WorkforceCustomerAccessReasonError);
    expect(repository.search).not.toHaveBeenCalled();
  });
});
