import { Injectable } from '@nestjs/common';
import {
  CommercialReleaseState,
  Prisma,
  type CommercialDataRelease,
} from '../../../../generated/prisma/client';
import { PrismaService } from '../../../../platform/database/prisma.service';
import {
  ActiveReleaseNotFoundError,
  ReleaseConcurrencyError,
  ReleaseNotFoundError,
} from '../../application/errors/release-workflow.errors';
import {
  assertSourceRevisionEligible,
  type SourceRevisionEvidence,
} from '../../../../platform/provenance/source-revision-policy';
import {
  CommercialReleaseWorkflowRepository,
  type ActivateCommercialReleaseCommand,
  type ApproveCommercialReleaseCommand,
  type RollbackCommercialReleaseCommand,
} from '../../application/ports/commercial-release-workflow.repository';
import {
  activateCatalogRelease,
  approveCatalogRelease,
  restoreCatalogRelease,
  supersedeCatalogRelease,
  type CatalogReleaseStateView,
} from '../../domain/catalog-release';
import {
  assertNoBlockingCommercialAnomaly,
  assertPriceOfferPublishable,
  VN_PUBLIC_VEHICLE_PRICE_POLICY,
} from '../../domain/commercial-facts';

const sourceSelection = {
  approvalEvidenceRef: true,
  approvalState: true,
  approvedAt: true,
  approvedByRef: true,
  checksum: true,
  classification: true,
  effectiveAt: true,
  expiresAt: true,
  freshnessTtlSeconds: true,
  ingestedAt: true,
  licenseId: true,
  observedAt: true,
  ownerRef: true,
  permittedPurposes: true,
  provenanceUri: true,
  retiredAt: true,
  submittedByRef: true,
} as const;

const releaseSelection = {
  activatedAt: true,
  activatedByRef: true,
  approvalEvidenceRef: true,
  approvedAt: true,
  approvedByRef: true,
  id: true,
  market: true,
  revision: true,
  state: true,
  submittedByRef: true,
  supersededAt: true,
} as const;

type TransactionClient = Prisma.TransactionClient;
type ReleaseRow = Pick<
  CommercialDataRelease,
  | 'activatedAt'
  | 'activatedByRef'
  | 'approvalEvidenceRef'
  | 'approvedAt'
  | 'approvedByRef'
  | 'id'
  | 'market'
  | 'revision'
  | 'state'
  | 'submittedByRef'
  | 'supersededAt'
>;

function stateView(release: ReleaseRow): CatalogReleaseStateView {
  return {
    ...release,
    state: release.state.toLowerCase() as CatalogReleaseStateView['state'],
  };
}

function sourceEvidence(
  source: Record<string, unknown>,
): SourceRevisionEvidence {
  return {
    ...(source as unknown as SourceRevisionEvidence),
    approvalState: String(source.approvalState).toLowerCase() as
      'approved' | 'pending' | 'rejected' | 'retired',
    classification: String(source.classification).toLowerCase() as
      'public' | 'internal' | 'confidential' | 'restricted',
  };
}

async function findRelease(
  transaction: TransactionClient,
  releaseId: string,
): Promise<ReleaseRow> {
  const release = await transaction.commercialDataRelease.findUnique({
    select: releaseSelection,
    where: { id: releaseId },
  });
  if (release === null) throw new ReleaseNotFoundError('commercial', releaseId);
  return release;
}

async function assertPublicationEligible(
  transaction: TransactionClient,
  releaseId: string,
  now: Date,
): Promise<void> {
  const release = await transaction.commercialDataRelease.findUnique({
    select: {
      market: true,
      priceOffers: {
        select: {
          amountMinor: true,
          anomalies: {
            select: { disposition: true, ruleCode: true, severity: true },
          },
          channel: true,
          currency: true,
          market: true,
          priceType: true,
          sourceRevision: { select: sourceSelection },
          validFrom: true,
          validTo: true,
        },
      },
      promotions: {
        select: {
          anomalies: {
            select: { disposition: true, ruleCode: true, severity: true },
          },
          sourceRevision: { select: sourceSelection },
        },
      },
      sourceRevision: { select: sourceSelection },
    },
    where: { id: releaseId },
  });
  if (release === null) throw new ReleaseNotFoundError('commercial', releaseId);
  if (release.priceOffers.length === 0) {
    throw new Error('Commercial release has no price offer.');
  }

  assertSourceRevisionEligible(
    sourceEvidence(release.sourceRevision),
    'vehicle-commercial-data',
    now,
  );
  for (const offer of release.priceOffers) {
    if (offer.market !== release.market) {
      throw new Error('Commercial release and price offer markets differ.');
    }
    assertPriceOfferPublishable(
      {
        amountMinor: offer.amountMinor,
        channel: offer.channel.toLowerCase() as
          'public' | 'retail' | 'fleet' | 'employee',
        currency: offer.currency,
        market: offer.market,
        priceType: offer.priceType.toLowerCase() as
          'msrp' | 'list' | 'option' | 'service',
        source: sourceEvidence(offer.sourceRevision),
        validFrom: offer.validFrom,
        validTo: offer.validTo,
      },
      offer.anomalies.map((anomaly) => ({
        disposition: anomaly.disposition.toLowerCase() as
          'open' | 'accepted' | 'rejected' | 'resolved',
        ruleCode: anomaly.ruleCode,
        severity: anomaly.severity.toLowerCase() as 'warning' | 'blocking',
      })),
      VN_PUBLIC_VEHICLE_PRICE_POLICY,
      now,
    );
  }
  for (const promotion of release.promotions) {
    assertSourceRevisionEligible(
      sourceEvidence(promotion.sourceRevision),
      'vehicle-commercial-data',
      now,
    );
    assertNoBlockingCommercialAnomaly(
      promotion.anomalies.map((anomaly) => ({
        disposition: anomaly.disposition.toLowerCase() as
          'open' | 'accepted' | 'rejected' | 'resolved',
        ruleCode: anomaly.ruleCode,
        severity: anomaly.severity.toLowerCase() as 'warning' | 'blocking',
      })),
    );
  }
}

async function marketLock(
  transaction: TransactionClient,
  market: string,
): Promise<void> {
  await transaction.$executeRaw`
    SELECT pg_advisory_xact_lock(
      hashtextextended(${`commercial-release:${market}`}, 0)
    )
  `;
}

async function writeEvidence(
  transaction: TransactionClient,
  input: {
    readonly action: string;
    readonly actorRef: string;
    readonly correlationId: string;
    readonly eventType: string;
    readonly market: string;
    readonly releaseId: string;
    readonly revision: number;
  },
): Promise<void> {
  await transaction.auditEvent.create({
    data: {
      action: input.action,
      actorRef: input.actorRef,
      actorType: 'workforce',
      correlationId: input.correlationId,
      metadata: { market: input.market, revision: input.revision },
      outcome: 'succeeded',
      resourceId: input.releaseId,
      resourceType: 'commercial_data_release',
    },
  });
  await transaction.outboxEvent.create({
    data: {
      aggregateId: input.releaseId,
      aggregateType: 'commercial_data_release',
      correlationId: input.correlationId,
      eventType: input.eventType,
      eventVersion: 1,
      payload: {
        market: input.market,
        releaseId: input.releaseId,
        revision: input.revision,
      },
    },
  });
}

@Injectable()
export class PrismaCommercialReleaseWorkflowRepository extends CommercialReleaseWorkflowRepository {
  constructor(private readonly prisma: PrismaService) {
    super();
  }

  approve(
    command: ApproveCommercialReleaseCommand,
  ): Promise<CatalogReleaseStateView> {
    return this.prisma.$transaction(
      async (transaction) => {
        const current = await findRelease(transaction, command.releaseId);
        if (current.revision !== command.expectedRevision) {
          throw new ReleaseConcurrencyError('commercial', current.id);
        }
        await assertPublicationEligible(transaction, current.id, command.now);
        const patch = approveCatalogRelease(
          stateView(current),
          command.reviewerRef,
          command.evidenceRef,
          command.now,
        );
        const result = await transaction.commercialDataRelease.updateMany({
          data: {
            approvalEvidenceRef: patch.approvalEvidenceRef,
            approvedAt: patch.approvedAt,
            approvedByRef: patch.approvedByRef,
            revision: patch.revision,
            state: CommercialReleaseState.APPROVED,
          },
          where: {
            id: current.id,
            revision: current.revision,
            state: CommercialReleaseState.DRAFT,
          },
        });
        if (result.count !== 1) {
          throw new ReleaseConcurrencyError('commercial', current.id);
        }
        await writeEvidence(transaction, {
          action: 'commercial_data.release.approve',
          actorRef: command.reviewerRef,
          correlationId: command.correlationId,
          eventType: 'commercial_data.release.approved',
          market: current.market,
          releaseId: current.id,
          revision: patch.revision,
        });
        return stateView(await findRelease(transaction, current.id));
      },
      { isolationLevel: Prisma.TransactionIsolationLevel.Serializable },
    );
  }

  activate(
    command: ActivateCommercialReleaseCommand,
  ): Promise<CatalogReleaseStateView> {
    return this.prisma.$transaction(
      async (transaction) => {
        const candidate = await findRelease(transaction, command.releaseId);
        await marketLock(transaction, candidate.market);
        const current = await findRelease(transaction, command.releaseId);
        if (current.revision !== command.expectedRevision) {
          throw new ReleaseConcurrencyError('commercial', current.id);
        }
        await assertPublicationEligible(transaction, current.id, command.now);
        const activation = activateCatalogRelease(
          stateView(current),
          command.actorRef,
          command.now,
        );
        const active = await transaction.commercialDataRelease.findFirst({
          select: releaseSelection,
          where: {
            id: { not: current.id },
            market: current.market,
            state: CommercialReleaseState.ACTIVE,
          },
        });
        if (active !== null) {
          const supersession = supersedeCatalogRelease(
            stateView(active),
            command.now,
          );
          const result = await transaction.commercialDataRelease.updateMany({
            data: {
              revision: supersession.revision,
              state: CommercialReleaseState.SUPERSEDED,
              supersededAt: supersession.supersededAt,
            },
            where: {
              id: active.id,
              revision: active.revision,
              state: CommercialReleaseState.ACTIVE,
            },
          });
          if (result.count !== 1) {
            throw new ReleaseConcurrencyError('commercial', active.id);
          }
        }
        const result = await transaction.commercialDataRelease.updateMany({
          data: {
            activatedAt: activation.activatedAt,
            activatedByRef: activation.activatedByRef,
            revision: activation.revision,
            state: CommercialReleaseState.ACTIVE,
            supersededAt: null,
          },
          where: {
            id: current.id,
            revision: current.revision,
            state: CommercialReleaseState.APPROVED,
          },
        });
        if (result.count !== 1) {
          throw new ReleaseConcurrencyError('commercial', current.id);
        }
        await writeEvidence(transaction, {
          action: 'commercial_data.release.activate',
          actorRef: command.actorRef,
          correlationId: command.correlationId,
          eventType: 'commercial_data.release.activated',
          market: current.market,
          releaseId: current.id,
          revision: activation.revision,
        });
        return stateView(await findRelease(transaction, current.id));
      },
      { isolationLevel: Prisma.TransactionIsolationLevel.Serializable },
    );
  }

  rollback(
    command: RollbackCommercialReleaseCommand,
  ): Promise<CatalogReleaseStateView> {
    return this.prisma.$transaction(
      async (transaction) => {
        const initialTarget = await findRelease(
          transaction,
          command.targetReleaseId,
        );
        await marketLock(transaction, initialTarget.market);
        const target = await findRelease(transaction, command.targetReleaseId);
        if (target.revision !== command.expectedTargetRevision) {
          throw new ReleaseConcurrencyError('commercial', target.id);
        }
        await assertPublicationEligible(transaction, target.id, command.now);
        const current = await transaction.commercialDataRelease.findFirst({
          select: releaseSelection,
          where: {
            market: target.market,
            state: CommercialReleaseState.ACTIVE,
          },
        });
        if (current === null) {
          throw new ActiveReleaseNotFoundError('commercial', target.market);
        }
        if (current.revision !== command.expectedCurrentRevision) {
          throw new ReleaseConcurrencyError('commercial', current.id);
        }
        const supersession = supersedeCatalogRelease(
          stateView(current),
          command.now,
        );
        const restoration = restoreCatalogRelease(
          stateView(target),
          command.actorRef,
          command.now,
        );
        const superseded = await transaction.commercialDataRelease.updateMany({
          data: {
            revision: supersession.revision,
            state: CommercialReleaseState.SUPERSEDED,
            supersededAt: supersession.supersededAt,
          },
          where: {
            id: current.id,
            revision: current.revision,
            state: CommercialReleaseState.ACTIVE,
          },
        });
        const restored = await transaction.commercialDataRelease.updateMany({
          data: {
            activatedAt: restoration.activatedAt,
            activatedByRef: restoration.activatedByRef,
            revision: restoration.revision,
            state: CommercialReleaseState.ACTIVE,
            supersededAt: null,
          },
          where: {
            id: target.id,
            revision: target.revision,
            state: CommercialReleaseState.SUPERSEDED,
          },
        });
        if (superseded.count !== 1 || restored.count !== 1) {
          throw new ReleaseConcurrencyError('commercial', target.id);
        }
        await writeEvidence(transaction, {
          action: 'commercial_data.release.rollback',
          actorRef: command.actorRef,
          correlationId: command.correlationId,
          eventType: 'commercial_data.release.restored',
          market: target.market,
          releaseId: target.id,
          revision: restoration.revision,
        });
        return stateView(await findRelease(transaction, target.id));
      },
      { isolationLevel: Prisma.TransactionIsolationLevel.Serializable },
    );
  }
}
