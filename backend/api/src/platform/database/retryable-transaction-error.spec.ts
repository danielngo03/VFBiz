import { isRetryableTransactionError } from './retryable-transaction-error';

describe('isRetryableTransactionError', () => {
  it.each(['P2002', 'P2034'])('accepts Prisma code %s', (code) => {
    expect(isRetryableTransactionError({ code })).toBe(true);
  });

  it.each(['TransactionWriteConflict', 'UniqueConstraintViolation'])(
    'accepts PostgreSQL driver kind %s',
    (kind) => {
      expect(
        isRetryableTransactionError({
          cause: { kind },
          name: 'DriverAdapterError',
        }),
      ).toBe(true);
    },
  );

  it.each([
    new Error('database unavailable'),
    null,
    { cause: { kind: 'ForeignKeyConstraintViolation' } },
    { code: 'P2003' },
  ])('rejects non-retryable error %#', (error) => {
    expect(isRetryableTransactionError(error)).toBe(false);
  });
});
