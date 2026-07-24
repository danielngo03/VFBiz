type ErrorRecord = Record<string, unknown>;

const RETRYABLE_PRISMA_CODES = new Set(['P2002', 'P2034']);
const RETRYABLE_DRIVER_KINDS = new Set([
  'TransactionWriteConflict',
  'UniqueConstraintViolation',
]);

function isRecord(value: unknown): value is ErrorRecord {
  return typeof value === 'object' && value !== null;
}

export function isRetryableTransactionError(error: unknown): boolean {
  if (!isRecord(error)) return false;

  if (
    typeof error.code === 'string' &&
    RETRYABLE_PRISMA_CODES.has(error.code)
  ) {
    return true;
  }

  if (!isRecord(error.cause) || typeof error.cause.kind !== 'string') {
    return false;
  }

  return RETRYABLE_DRIVER_KINDS.has(error.cause.kind);
}
