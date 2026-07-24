import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import { PrismaService } from '../../../../platform/database/prisma.service';
import type { RecordConsentInput } from '../../application/ports/customer-account.repository';
import {
  CustomerConsentBatchValidationError,
  CustomerConsentPolicyUnavailableError,
  CustomerIdempotencyConflictError,
} from '../../domain/customer-account';
import { PrismaCustomerAccountRepository } from './prisma-customer-account.repository';

const principal = (subject = 'synthetic-customer-001'): AccessPrincipal => ({
  authenticationContext: 'urn:vfbiz:loa:1',
  authenticationMethods: ['pwd'],
  audience: ['vfbiz-customer-api'],
  authorizedParty: 'vfbiz-customer-bff',
  issuer: 'https://identity.test.invalid/realms/customer',
  realm: 'customer',
  scopes: ['consent:read', 'consent:write'],
  sessionId: 'synthetic-session-001',
  subject,
});

const consent = (
  purpose: 'analytics' | 'marketing_email',
  overrides: Partial<RecordConsentInput> = {},
): RecordConsentInput => ({
  correlationId:
    purpose === 'analytics'
      ? '22222222-2222-4222-a222-222222222222'
      : '33333333-3333-4333-a333-333333333333',
  idempotencyKey: 'synthetic-consent-request-0001',
  policyVersion: 'synthetic-policy-2026-07',
  principal: principal(),
  purpose,
  source: 'customer_portal',
  state: 'granted',
  ...overrides,
});

function transactionDouble(
  existing: readonly object[] = [],
  policyPurposes: readonly ('analytics' | 'marketing_email')[] = [
    'analytics',
    'marketing_email',
  ],
) {
  const createMany = jest.fn<
    Promise<{ count: number }>,
    [
      {
        data: readonly { purpose: string }[];
        skipDuplicates: boolean;
      },
    ]
  >(() => Promise.resolve({ count: 2 }));
  return {
    auditEvent: { create: jest.fn().mockResolvedValue({}) },
    consentPolicy: {
      findMany: jest.fn().mockResolvedValue(
        policyPurposes.map((purpose) => ({
          policyVersion: 'synthetic-policy-2026-07',
          purpose,
        })),
      ),
    },
    consentEvent: {
      createMany,
      findMany: jest
        .fn()
        .mockResolvedValueOnce(existing)
        .mockResolvedValueOnce([]),
    },
    customerProfile: {
      findFirst: jest
        .fn()
        .mockResolvedValue({ id: '11111111-1111-4111-a111-111111111111' }),
    },
    outboxEvent: { create: jest.fn().mockResolvedValue({}) },
  };
}

function repositoryWithTransaction(
  transaction: ReturnType<typeof transactionDouble>,
  failures: Error[] = [],
) {
  let transactionOptions: unknown;
  const execute = jest.fn(
    async (callback: (client: unknown) => unknown, options?: unknown) => {
      transactionOptions = options;
      const failure = failures.shift();
      if (failure !== undefined) throw failure;
      return await Promise.resolve(callback(transaction));
    },
  );
  const prisma = { $transaction: execute } as unknown as PrismaService;
  return {
    execute,
    repository: new PrismaCustomerAccountRepository(prisma),
    transaction,
    transactionOptions: () => transactionOptions,
  };
}

function prismaError(code: string): Error {
  return Object.assign(new Error(`Synthetic Prisma error ${code}`), { code });
}

describe('PrismaCustomerAccountRepository consent transaction contract', () => {
  it('writes the complete consent batch in one serializable transaction', async () => {
    const fixture = repositoryWithTransaction(transactionDouble());

    await fixture.repository.recordConsents([
      consent('analytics'),
      consent('marketing_email'),
    ]);

    expect(fixture.execute).toHaveBeenCalledTimes(1);
    expect(fixture.transactionOptions()).toEqual({
      isolationLevel: 'Serializable',
    });
    expect(fixture.transaction.consentEvent.createMany).toHaveBeenCalledTimes(
      1,
    );
    const create =
      fixture.transaction.consentEvent.createMany.mock.calls[0]?.[0];
    expect(create?.skipDuplicates).toBe(false);
    expect(create?.data.map((record) => record.purpose)).toEqual([
      'analytics',
      'marketing_email',
    ]);
    expect(fixture.transaction.auditEvent.create).toHaveBeenCalledTimes(1);
    expect(fixture.transaction.outboxEvent.create).toHaveBeenCalledTimes(1);
  });

  it('rejects a partial historical replay without writing missing events', async () => {
    const fixture = repositoryWithTransaction(
      transactionDouble([
        {
          idempotencyKeyHash: 'a'.repeat(64),
          purpose: 'analytics',
          requestHash: 'b'.repeat(64),
        },
      ]),
    );

    await expect(
      fixture.repository.recordConsents([
        consent('analytics'),
        consent('marketing_email'),
      ]),
    ).rejects.toBeInstanceOf(CustomerIdempotencyConflictError);
    expect(fixture.transaction.consentEvent.createMany).not.toHaveBeenCalled();
  });

  it('fails closed when a client supplies an inactive policy version', async () => {
    const fixture = repositoryWithTransaction(transactionDouble([], []));

    await expect(
      fixture.repository.recordConsents([consent('analytics')]),
    ).rejects.toBeInstanceOf(CustomerConsentPolicyUnavailableError);
    expect(fixture.transaction.consentEvent.createMany).not.toHaveBeenCalled();
    expect(fixture.transaction.auditEvent.create).not.toHaveBeenCalled();
    expect(fixture.transaction.outboxEvent.create).not.toHaveBeenCalled();
  });

  it('rejects duplicate purposes and mixed subjects before opening a transaction', async () => {
    const duplicateFixture = repositoryWithTransaction(transactionDouble());
    await expect(
      duplicateFixture.repository.recordConsents([
        consent('analytics'),
        consent('analytics', {
          correlationId: '44444444-4444-4444-a444-444444444444',
        }),
      ]),
    ).rejects.toBeInstanceOf(CustomerConsentBatchValidationError);
    expect(duplicateFixture.execute).not.toHaveBeenCalled();

    const mixedSubjectFixture = repositoryWithTransaction(transactionDouble());
    await expect(
      mixedSubjectFixture.repository.recordConsents([
        consent('analytics'),
        consent('marketing_email', {
          principal: principal('synthetic-customer-002'),
        }),
      ]),
    ).rejects.toBeInstanceOf(CustomerConsentBatchValidationError);
    expect(mixedSubjectFixture.execute).not.toHaveBeenCalled();
  });

  it('retries a serialization conflict at most within the bounded policy', async () => {
    const fixture = repositoryWithTransaction(
      transactionDouble([], ['analytics']),
      [prismaError('P2034'), prismaError('P2034')],
    );

    await fixture.repository.recordConsents([consent('analytics')]);

    expect(fixture.execute).toHaveBeenCalledTimes(3);
    expect(fixture.transaction.consentEvent.createMany).toHaveBeenCalledTimes(
      1,
    );
  });

  it('does not retry unknown persistence failures', async () => {
    const failure = new Error('synthetic persistence failure');
    const fixture = repositoryWithTransaction(
      transactionDouble([], ['analytics']),
      [failure],
    );

    await expect(
      fixture.repository.recordConsents([consent('analytics')]),
    ).rejects.toBe(failure);
    expect(fixture.execute).toHaveBeenCalledTimes(1);
  });
});
