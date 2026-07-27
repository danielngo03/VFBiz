import { createHash } from 'node:crypto';
import { Injectable } from '@nestjs/common';
import { Prisma } from '../../../../generated/prisma/client';
import { PrismaService } from '../../../../platform/database/prisma.service';
import { isRetryableTransactionError } from '../../../../platform/database/retryable-transaction-error';
import {
  IdempotencyRepository,
  type CompleteIdempotencyKeyInput,
  type IdempotencyReservation,
  type ReserveIdempotencyKeyInput,
} from '../../application/ports/idempotency.repository';

const MAX_SERIALIZABLE_ATTEMPTS = 3;

function hash(value: string): string {
  return createHash('sha256').update(value).digest('hex');
}

@Injectable()
export class PrismaIdempotencyRepository implements IdempotencyRepository {
  constructor(private readonly prisma: PrismaService) {}

  async reserve(
    input: ReserveIdempotencyKeyInput,
  ): Promise<IdempotencyReservation> {
    const keyHash = hash(input.key);
    for (let attempt = 1; attempt <= MAX_SERIALIZABLE_ATTEMPTS; attempt += 1) {
      try {
        return await this.prisma.$transaction(
          async (tx) => {
            const existing = await tx.idempotencyRecord.findUnique({
              where: {
                namespace_keyHash: {
                  namespace: input.namespace,
                  keyHash,
                },
              },
            });
            const expiresAt = new Date(Date.now() + input.ttlSeconds * 1000);
            if (existing !== null) {
              if (existing.requestHash !== input.requestHash) {
                return { kind: 'conflict' } as const;
              }
              if (existing.status === 'completed') {
                return {
                  kind: 'replay',
                  responseStatus: existing.responseStatus ?? 200,
                  responseBody: existing.responseBody,
                } as const;
              }
              if (existing.expiresAt > new Date()) {
                // Same key, same request, still in flight (or a prior
                // attempt crashed before completing) and not yet reclaimable
                // — fail closed rather than guess at an outcome that was
                // never recorded.
                return { kind: 'conflict' } as const;
              }
              // The prior reservation crashed or otherwise never completed,
              // and its TTL has elapsed: reclaim it as a fresh attempt
              // rather than stranding this key forever.
              await tx.idempotencyRecord.update({
                data: {
                  expiresAt,
                  responseBody: Prisma.JsonNull,
                  responseStatus: null,
                  status: 'pending',
                },
                where: { id: existing.id },
              });
              return { kind: 'reserved' } as const;
            }
            await tx.idempotencyRecord.create({
              data: {
                namespace: input.namespace,
                keyHash,
                requestHash: input.requestHash,
                status: 'pending',
                expiresAt,
              },
            });
            return { kind: 'reserved' } as const;
          },
          { isolationLevel: Prisma.TransactionIsolationLevel.Serializable },
        );
      } catch (error) {
        if (
          !isRetryableTransactionError(error) ||
          attempt === MAX_SERIALIZABLE_ATTEMPTS
        ) {
          throw error;
        }
      }
    }
    throw new Error('idempotency reservation exhausted retries');
  }

  async complete(input: CompleteIdempotencyKeyInput): Promise<void> {
    const keyHash = hash(input.key);
    await this.prisma.idempotencyRecord.update({
      where: {
        namespace_keyHash: {
          namespace: input.namespace,
          keyHash,
        },
      },
      data: {
        status: 'completed',
        responseStatus: input.responseStatus,
        responseBody: input.responseBody as Prisma.InputJsonValue,
      },
    });
  }
}
