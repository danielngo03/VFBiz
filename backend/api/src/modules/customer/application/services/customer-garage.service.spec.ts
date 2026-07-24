import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import { CheckVehicleVariantEligibilityService } from '../../../product';
import type { CustomerProfileView } from '../../domain/customer-account';
import {
  CustomerGarageVariantUnavailableError,
  type CustomerGarageEntryView,
} from '../../domain/customer-garage';
import { CustomerAccountService } from './customer-account.service';
import { CustomerGarageService } from './customer-garage.service';

const principal: AccessPrincipal = {
  authenticationContext: 'urn:vfbiz:loa:1',
  authenticationMethods: ['pwd'],
  audience: ['vfbiz-customer-api'],
  authorizedParty: 'vfbiz-customer-bff',
  issuer: 'https://id.example/realms/customer',
  realm: 'customer',
  scopes: ['garage:read', 'garage:write'],
  sessionId: 'session-1',
  subject: 'subject-1',
};

const profile: CustomerProfileView = {
  communicationPreferences: { email: false, push: false, sms: false },
  displayName: null,
  locale: 'vi',
  market: 'VN',
  timezone: 'Asia/Ho_Chi_Minh',
  updatedAt: new Date('2026-07-23T08:00:00.000Z'),
  version: 1,
};
const correlationId = '11111111-1111-4111-a111-111111111111';

const entry: CustomerGarageEntryView = {
  claimedVehicleVariantId: '1f7f4e42-7a45-47ce-a798-f0271301fe97',
  createdAt: new Date('2026-07-23T08:01:00.000Z'),
  id: '49028ab3-a07c-4b82-8527-ae494828206a',
  isPrimary: true,
  nickname: 'Xe gia đình',
  ownershipStatus: 'unverified',
  source: 'self-reported',
  status: 'active',
  updatedAt: new Date('2026-07-23T08:01:00.000Z'),
  version: 1,
};

describe('CustomerGarageService', () => {
  const accounts = {
    getProfile: jest.fn().mockResolvedValue(profile),
  };
  const catalog = {
    isSelectable: jest.fn().mockResolvedValue(true),
  };
  const repository = {
    archive: jest.fn().mockResolvedValue({ ...entry, status: 'archived' }),
    create: jest.fn().mockResolvedValue(entry),
    findCreateReplay: jest.fn().mockResolvedValue(null),
    list: jest.fn().mockResolvedValue([entry]),
    update: jest.fn().mockResolvedValue({ ...entry, nickname: 'VF 8' }),
  };
  const service = new CustomerGarageService(
    accounts as unknown as CustomerAccountService,
    catalog as unknown as CheckVehicleVariantEligibilityService,
    repository,
  );

  beforeEach(() => jest.clearAllMocks());

  it('provisions the profile and validates the market release before create', async () => {
    await expect(
      service.create(principal, correlationId, 'garage-create-0001', {
        claimedVehicleVariantId: entry.claimedVehicleVariantId,
        nickname: entry.nickname,
      }),
    ).resolves.toEqual(entry);

    expect(accounts.getProfile).toHaveBeenCalledWith(principal);
    expect(catalog.isSelectable).toHaveBeenCalledWith(
      entry.claimedVehicleVariantId,
      'VN',
    );
    expect(repository.create).toHaveBeenCalledWith({
      claimedVehicleVariantId: entry.claimedVehicleVariantId,
      correlationId,
      idempotencyKey: 'garage-create-0001',
      isPrimary: false,
      nickname: entry.nickname,
      principal,
    });
  });

  it('replays an accepted idempotent create before consulting current catalog state', async () => {
    repository.findCreateReplay.mockResolvedValueOnce(entry);

    await expect(
      service.create(principal, correlationId, 'garage-create-0001', {
        claimedVehicleVariantId: entry.claimedVehicleVariantId,
        nickname: entry.nickname,
      }),
    ).resolves.toEqual(entry);
    expect(catalog.isSelectable).not.toHaveBeenCalled();
    expect(repository.create).not.toHaveBeenCalled();
  });

  it('fails closed when the claimed variant is not in a fresh active release', async () => {
    catalog.isSelectable.mockResolvedValueOnce(false);

    await expect(
      service.create(principal, correlationId, 'garage-create-0002', {
        claimedVehicleVariantId: entry.claimedVehicleVariantId,
      }),
    ).rejects.toBeInstanceOf(CustomerGarageVariantUnavailableError);
    expect(repository.create).not.toHaveBeenCalled();
  });

  it('provisions the subject before every subject-scoped read', async () => {
    await expect(service.list(principal)).resolves.toEqual([entry]);
    expect(accounts.getProfile).toHaveBeenCalledWith(principal);
    expect(repository.list).toHaveBeenCalledWith(principal);
  });
});
