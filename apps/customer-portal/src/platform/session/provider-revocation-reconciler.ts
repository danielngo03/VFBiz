import "server-only";
import { revokeToken } from "@/platform/auth/oidc";
import type { ProviderRevocationReconciliation } from "./contracts";
import {
  acquireProviderRevocationLease,
  abandonProviderRevocation,
  completeProviderRevocation,
  enqueueProviderRevocation,
  readDueProviderRevocations,
  releaseProviderRevocationLease,
  renewProviderRevocationLease,
  rescheduleProviderRevocation,
} from "./redis-token-vault";

const RETRY_DELAYS_MILLISECONDS = [
  60_000,
  5 * 60_000,
  15 * 60_000,
  60 * 60_000,
  6 * 60 * 60_000,
  24 * 60 * 60_000,
] as const;
const MAX_RETRY_ATTEMPTS = RETRY_DELAYS_MILLISECONDS.length;
const MAX_RETRY_AGE_MILLISECONDS = 7 * 24 * 60 * 60 * 1_000;

type RevokeProviderToken = (refreshToken: string) => Promise<boolean>;

export interface ProviderRevocationDrainResult {
  readonly confirmed: number;
  readonly leaseUnavailable: boolean;
  readonly retryRequired: number;
  readonly scanned: number;
}

function retryDelay(attemptCount: number): number {
  return (
    RETRY_DELAYS_MILLISECONDS[
      Math.min(attemptCount, RETRY_DELAYS_MILLISECONDS.length - 1)
    ] ?? RETRY_DELAYS_MILLISECONDS.at(-1)!
  );
}

export async function revokeOrEnqueueProviderToken(
  input: {
    readonly now?: Date;
    readonly providerSessionId: string;
    readonly refreshToken?: string;
  },
  revoke: RevokeProviderToken = revokeToken,
): Promise<ProviderRevocationReconciliation> {
  if (input.refreshToken === undefined) return "retry_required";
  if (await revoke(input.refreshToken)) return "confirmed";
  try {
    await enqueueProviderRevocation({
      providerSessionId: input.providerSessionId,
      refreshToken: input.refreshToken,
      ...(input.now === undefined ? {} : { now: input.now }),
    });
    return "pending";
  } catch {
    return "retry_required";
  }
}

export async function drainProviderRevocations(
  input: {
    readonly limit?: number;
    readonly now?: Date;
    readonly revoke?: RevokeProviderToken;
  } = {},
): Promise<ProviderRevocationDrainResult> {
  const lease = await acquireProviderRevocationLease();
  if (lease === null) {
    return {
      confirmed: 0,
      leaseUnavailable: true,
      retryRequired: 0,
      scanned: 0,
    };
  }
  const now = input.now ?? new Date();
  const revoke = input.revoke ?? revokeToken;
  let confirmed = 0;
  let leaseUnavailable = false;
  let retryRequired = 0;
  try {
    const tasks = await readDueProviderRevocations(now, input.limit);
    for (const task of tasks) {
      if (!(await renewProviderRevocationLease(lease))) {
        leaseUnavailable = true;
        break;
      }
      if (
        task.attemptCount >= MAX_RETRY_ATTEMPTS ||
        now.getTime() - task.createdAt.getTime() >=
          MAX_RETRY_AGE_MILLISECONDS
      ) {
        if (!(await abandonProviderRevocation(task, now, lease))) {
          leaseUnavailable = true;
          break;
        }
        retryRequired += 1;
        continue;
      }
      let revoked = false;
      try {
        revoked = await revoke(task.refreshToken);
      } catch {
        revoked = false;
      }
      if (!(await renewProviderRevocationLease(lease))) {
        leaseUnavailable = true;
        break;
      }
      if (revoked) {
        if (!(await completeProviderRevocation(task.id, lease))) {
          leaseUnavailable = true;
          break;
        }
        confirmed += 1;
        continue;
      }
      if (task.attemptCount + 1 >= MAX_RETRY_ATTEMPTS) {
        if (!(await abandonProviderRevocation(task, now, lease))) {
          leaseUnavailable = true;
          break;
        }
        retryRequired += 1;
        continue;
      }
      const nextAttemptAt = new Date(
        now.getTime() + retryDelay(task.attemptCount),
      );
      if (
        !(await rescheduleProviderRevocation(
          task,
          {
            attemptedAt: now,
            nextAttemptAt,
          },
          lease,
        ))
      ) {
        leaseUnavailable = true;
        break;
      }
      retryRequired += 1;
    }
    return {
      confirmed,
      leaseUnavailable,
      retryRequired,
      scanned: confirmed + retryRequired,
    };
  } finally {
    await releaseProviderRevocationLease(lease);
  }
}
