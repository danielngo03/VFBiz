import { Injectable } from '@nestjs/common';
import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import { PrismaService } from '../../../../platform/database/prisma.service';
import { isRetryableTransactionError } from '../../../../platform/database/retryable-transaction-error';
import { sessionReferenceFingerprint } from '../../../../platform/security/session-reference-fingerprint';
import {
  AccessSessionRepository,
  type BeginSessionRevocationResult,
} from '../../application/ports/access-session.repository';
import {
  AccessSessionNotFoundError,
  sessionStatus,
  type AccessSessionView,
  type ReconcileSessionObservation,
  type SessionRevocationReconciliation,
  type SessionRevocationState,
} from '../../domain/access-session';

const MAX_SERIALIZABLE_ATTEMPTS = 3;

const sessionSelection = {
  authenticatedAt: true,
  deviceLabel: true,
  emailVerified: true,
  expiresAt: true,
  id: true,
  lastSeenAt: true,
  mfaSatisfied: true,
  observationRevision: true,
  providerRoute: true,
  providerSessionSecretReference: true,
  revocationIntentAt: true,
  revocationNextRetryAt: true,
  revocationState: true,
  revocationVersion: true,
  revokedAt: true,
  sessionRefHash: true,
  ipPrefix: true,
  userAgentSummary: true,
} as const;

type SessionRecord = {
  readonly authenticatedAt: Date;
  readonly deviceLabel: string | null;
  readonly emailVerified: boolean | null;
  readonly expiresAt: Date;
  readonly id: string;
  readonly lastSeenAt: Date;
  readonly mfaSatisfied: boolean;
  readonly observationRevision: bigint;
  readonly providerRoute: string | null;
  readonly providerSessionSecretReference: string | null;
  readonly revocationIntentAt: Date | null;
  readonly revocationNextRetryAt: Date | null;
  readonly revocationState: string;
  readonly revocationVersion: number;
  readonly revokedAt: Date | null;
  readonly sessionRefHash: string;
  readonly ipPrefix: string | null;
  readonly userAgentSummary: string | null;
};

function toView(
  record: SessionRecord,
  currentSessionHash: string | null,
  now: Date,
): AccessSessionView {
  return {
    authenticatedAt: record.authenticatedAt,
    deviceLabel: record.deviceLabel,
    emailVerified: record.emailVerified,
    expiresAt: record.expiresAt,
    id: record.id,
    isCurrent: record.sessionRefHash === currentSessionHash,
    mfaSatisfied: record.mfaSatisfied,
    networkHint: record.ipPrefix,
    lastSeenAt: record.lastSeenAt,
    revokedAt: record.revokedAt,
    status: sessionStatus(record.revokedAt, record.expiresAt, now),
    userAgentSummary: record.userAgentSummary,
  };
}

function reconciliationFor(
  state: SessionRevocationState,
): SessionRevocationReconciliation {
  return state === 'none' ? 'pending' : state;
}

@Injectable()
export class PrismaAccessSessionRepository extends AccessSessionRepository {
  constructor(private readonly prisma: PrismaService) {
    super();
  }

  async list(
    principal: AccessPrincipal,
    now: Date,
  ): Promise<readonly AccessSessionView[]> {
    const records = await this.prisma.sessionProjection.findMany({
      orderBy: { lastSeenAt: 'desc' },
      select: sessionSelection,
      where: {
        identitySubject: {
          issuer: principal.issuer,
          realm: 'customer',
          status: 'active',
          subject: principal.subject,
        },
      },
    });
    const currentHash =
      principal.sessionId === null
        ? null
        : sessionReferenceFingerprint(principal, principal.sessionId);
    return records.map((record) => toView(record, currentHash, now));
  }

  async beginRevocation(
    principal: AccessPrincipal,
    projectionId: string,
    revokedAt: Date,
  ): Promise<BeginSessionRevocationResult> {
    const current = await this.findOwnedSession(principal, projectionId);
    const currentHash =
      principal.sessionId === null
        ? null
        : sessionReferenceFingerprint(principal, principal.sessionId);
    const state = current.revocationState as SessionRevocationState;
    const retryIsDue =
      current.revocationNextRetryAt === null ||
      current.revocationNextRetryAt.getTime() <= revokedAt.getTime();

    if (
      state === 'pending' ||
      state === 'confirmed' ||
      state === 'manual_review_required' ||
      (state === 'retry_required' && !retryIsDue)
    ) {
      return {
        dispatch: false,
        providerRoute: null,
        providerSessionSecretReference: null,
        reconciliation: reconciliationFor(state),
        revocationVersion: current.revocationVersion,
        session: toView(current, currentHash, revokedAt),
      };
    }

    const canDispatch =
      current.providerRoute === 'customer-ciam' &&
      current.providerSessionSecretReference !== null;
    const nextState = canDispatch ? 'pending' : 'manual_review_required';
    const claimed = await this.prisma.sessionProjection.updateMany({
      data: {
        revocationAttempt: { increment: 1 },
        revocationIntentAt:
          current.revocationIntentAt === null ? revokedAt : undefined,
        revocationLastAttemptAt: canDispatch ? revokedAt : undefined,
        revocationLastErrorCode: canDispatch
          ? null
          : 'CIAM_PROVIDER_REFERENCE_UNAVAILABLE',
        revocationNextRetryAt: null,
        revocationState: nextState,
        revocationVersion: { increment: 1 },
        revokedAt: current.revokedAt === null ? revokedAt : undefined,
      },
      where: {
        id: current.id,
        revocationState: state,
        revocationVersion: current.revocationVersion,
      },
    });
    const persisted = await this.prisma.sessionProjection.findUniqueOrThrow({
      select: sessionSelection,
      where: { id: current.id },
    });
    const wonClaim =
      claimed.count === 1 && persisted.revocationState === 'pending';

    return {
      dispatch: wonClaim,
      providerRoute: wonClaim ? 'customer-ciam' : null,
      providerSessionSecretReference: wonClaim
        ? persisted.providerSessionSecretReference
        : null,
      reconciliation: reconciliationFor(
        persisted.revocationState as SessionRevocationState,
      ),
      revocationVersion: persisted.revocationVersion,
      session: toView(persisted, currentHash, revokedAt),
    };
  }

  async completeRevocation(
    projectionId: string,
    revocationVersion: number,
    reconciliation: Exclude<SessionRevocationReconciliation, 'pending'>,
    completedAt: Date,
  ): Promise<void> {
    const retryAt =
      reconciliation === 'retry_required'
        ? new Date(completedAt.getTime() + 60_000)
        : null;
    await this.prisma.sessionProjection.updateMany({
      data: {
        revocationLastErrorCode:
          reconciliation === 'retry_required'
            ? 'CIAM_REVOCATION_RETRY_REQUIRED'
            : reconciliation === 'manual_review_required'
              ? 'CIAM_REVOCATION_MANUAL_REVIEW'
              : null,
        revocationNextRetryAt: retryAt,
        revocationState: reconciliation,
      },
      where: {
        id: projectionId,
        revocationState: 'pending',
        revocationVersion,
      },
    });
  }

  async reconcile(
    observation: ReconcileSessionObservation,
    now: Date,
  ): Promise<AccessSessionView> {
    return this.withSerializableRetry(() =>
      this.prisma.$transaction(
        async (transaction) => {
          const identity = await transaction.identitySubject.upsert({
            create: {
              issuer: observation.issuer,
              realm: observation.realm,
              subject: observation.subject,
            },
            select: { id: true, realm: true, status: true },
            update: {},
            where: {
              issuer_subject: {
                issuer: observation.issuer,
                subject: observation.subject,
              },
            },
          });
          if (identity.realm !== 'customer' || identity.status !== 'active') {
            throw new AccessSessionNotFoundError();
          }

          const fingerprint = sessionReferenceFingerprint(
            observation,
            observation.sessionReference,
          );
          const existing = await transaction.sessionProjection.findUnique({
            select: sessionSelection,
            where: { sessionRefHash: fingerprint },
          });
          if (existing === null) {
            const created = await transaction.sessionProjection.create({
              data: {
                authenticatedAt: observation.authenticatedAt,
                deviceLabel: observation.deviceLabel,
                emailVerified: observation.emailVerified,
                expiresAt: observation.expiresAt,
                identitySubjectId: identity.id,
                ipPrefix: observation.ipPrefix,
                lastSeenAt: observation.lastSeenAt,
                mfaSatisfied: observation.mfaSatisfied,
                observationObservedAt: observation.observedAt,
                observationRevision: observation.eventRevision,
                providerRoute:
                  observation.providerSessionSecretReference === null
                    ? null
                    : observation.providerRoute,
                providerSessionRefHash: null,
                providerSessionSecretReference:
                  observation.providerSessionSecretReference,
                revokedAt: observation.revokedAt,
                sessionRefHash: fingerprint,
                userAgentSummary: observation.userAgentSummary,
              },
              select: sessionSelection,
            });
            return toView(created, fingerprint, now);
          }
          if (
            existing.revokedAt !== null ||
            existing.expiresAt.getTime() <= now.getTime() ||
            observation.eventRevision <= existing.observationRevision
          ) {
            return toView(existing, fingerprint, now);
          }

          await transaction.sessionProjection.updateMany({
            data: {
              deviceLabel: observation.deviceLabel,
              emailVerified: observation.emailVerified,
              expiresAt: observation.expiresAt,
              lastSeenAt: observation.lastSeenAt,
              mfaSatisfied: observation.mfaSatisfied,
              observationObservedAt: observation.observedAt,
              observationRevision: observation.eventRevision,
              providerRoute:
                observation.providerSessionSecretReference === null
                  ? null
                  : observation.providerRoute,
              providerSessionSecretReference:
                observation.providerSessionSecretReference,
              revokedAt: observation.revokedAt,
              ipPrefix: observation.ipPrefix,
              userAgentSummary: observation.userAgentSummary,
            },
            where: {
              id: existing.id,
              observationRevision: { lt: observation.eventRevision },
              revokedAt: null,
            },
          });
          const persisted =
            await transaction.sessionProjection.findUniqueOrThrow({
              select: sessionSelection,
              where: { id: existing.id },
            });
          return toView(persisted, fingerprint, now);
        },
        { isolationLevel: 'Serializable' },
      ),
    );
  }

  async revokeCurrent(
    principal: AccessPrincipal,
    revokedAt: Date,
  ): Promise<void> {
    if (principal.realm !== 'customer' || principal.sessionId === null) return;
    await this.prisma.sessionProjection.updateMany({
      data: {
        revocationIntentAt: revokedAt,
        revocationLastErrorCode: 'LOCAL_LOGOUT',
        revocationState: 'manual_review_required',
        revocationVersion: { increment: 1 },
        revokedAt,
      },
      where: {
        identitySubject: {
          issuer: principal.issuer,
          realm: 'customer',
          subject: principal.subject,
        },
        revokedAt: null,
        sessionRefHash: sessionReferenceFingerprint(
          principal,
          principal.sessionId,
        ),
      },
    });
  }

  async revokeAll(
    principal: AccessPrincipal,
    revokedAt: Date,
  ): Promise<number> {
    if (principal.realm !== 'customer') return 0;
    const result = await this.prisma.sessionProjection.updateMany({
      data: {
        revocationIntentAt: revokedAt,
        revocationLastErrorCode: 'CUSTOMER_LOGOUT_ALL',
        revocationState: 'pending',
        revocationVersion: { increment: 1 },
        revokedAt,
      },
      where: {
        identitySubject: {
          issuer: principal.issuer,
          realm: 'customer',
          status: 'active',
          subject: principal.subject,
        },
        expiresAt: { gt: revokedAt },
        revokedAt: null,
      },
    });
    return result.count;
  }

  private async withSerializableRetry<T>(
    operation: () => Promise<T>,
  ): Promise<T> {
    for (let attempt = 1; ; attempt += 1) {
      try {
        return await operation();
      } catch (error) {
        if (
          attempt >= MAX_SERIALIZABLE_ATTEMPTS ||
          !isRetryableTransactionError(error)
        ) {
          throw error;
        }
      }
    }
  }

  private async findOwnedSession(
    principal: AccessPrincipal,
    projectionId: string,
  ): Promise<SessionRecord> {
    const session = await this.prisma.sessionProjection.findFirst({
      select: sessionSelection,
      where: {
        id: projectionId,
        identitySubject: {
          issuer: principal.issuer,
          realm: 'customer',
          status: 'active',
          subject: principal.subject,
        },
      },
    });
    if (session === null) throw new AccessSessionNotFoundError();
    return session;
  }
}
