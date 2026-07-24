import { Injectable } from '@nestjs/common';
import {
  Prisma,
  type VehicleCatalogRelease,
} from '../../../../generated/prisma/client';
import { VehicleCatalogReleaseState } from '../../../../generated/prisma/enums';
import { PrismaService } from '../../../../platform/database/prisma.service';
import {
  ActiveReleaseNotFoundError,
  ReleaseConcurrencyError,
  ReleaseNotFoundError,
} from '../../application/errors/release-workflow.errors';
import {
  CatalogReleaseWorkflowRepository,
  type ActivateCatalogReleaseCommand,
  type ApproveCatalogReleaseCommand,
  type RollbackCatalogReleaseCommand,
} from '../../application/ports/catalog-release-workflow.repository';
import {
  assertCatalogFactProvenance,
  assertPublishableCatalogSource,
  requiredVariantFactGroups,
} from '../../domain/catalog-publication-policy';
import {
  activateCatalogRelease,
  approveCatalogRelease,
  restoreCatalogRelease,
  supersedeCatalogRelease,
  type CatalogReleaseStateView,
} from '../../domain/catalog-release';

const publicationSourceSelection = {
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

const releaseWorkflowSelection = {
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
type ReleaseWorkflowRow = Pick<
  VehicleCatalogRelease,
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

function stateView(release: ReleaseWorkflowRow): CatalogReleaseStateView {
  return {
    ...release,
    state: release.state.toLowerCase() as CatalogReleaseStateView['state'],
  };
}

async function findRelease(
  transaction: TransactionClient,
  releaseId: string,
): Promise<ReleaseWorkflowRow> {
  const release = await transaction.vehicleCatalogRelease.findUnique({
    select: releaseWorkflowSelection,
    where: { id: releaseId },
  });
  if (release === null) throw new ReleaseNotFoundError('catalog', releaseId);
  return release;
}

async function assertPublicationEligible(
  transaction: TransactionClient,
  releaseId: string,
  now: Date,
): Promise<void> {
  const release = await transaction.vehicleCatalogRelease.findUnique({
    select: {
      factProvenance: {
        select: {
          factGroup: true,
          sourceRevision: { select: publicationSourceSelection },
          subjectRef: true,
          subjectType: true,
        },
      },
      id: true,
      modelRevisions: { select: { vehicleModelId: true } },
      sourceRevision: { select: publicationSourceSelection },
      variantRevisions: {
        select: {
          connectorStandards: true,
          declaredRangeKm: true,
          drivetrain: true,
          grossBatteryCapacityKwh: true,
          maximumAcChargePowerKw: true,
          maximumDcChargePowerKw: true,
          seats: true,
          usableBatteryCapacityKwh: true,
          vehicleVariantId: true,
        },
      },
    },
    where: { id: releaseId },
  });
  if (release === null) throw new ReleaseNotFoundError('catalog', releaseId);
  if (
    release.modelRevisions.length === 0 ||
    release.variantRevisions.length === 0
  ) {
    throw new Error('Catalog release has no model or variant membership.');
  }

  assertPublishableCatalogSource(release.sourceRevision, now);
  assertCatalogFactProvenance(
    release.id,
    new Set(release.modelRevisions.map((model) => model.vehicleModelId)),
    release.variantRevisions.map((variant) => ({
      id: variant.vehicleVariantId,
      requiredGroups: requiredVariantFactGroups(variant),
    })),
    release.factProvenance,
    now,
  );
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
      metadata: {
        market: input.market,
        revision: input.revision,
      },
      outcome: 'succeeded',
      resourceId: input.releaseId,
      resourceType: 'vehicle_catalog_release',
    },
  });
  await transaction.outboxEvent.create({
    data: {
      aggregateId: input.releaseId,
      aggregateType: 'vehicle_catalog_release',
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

async function marketLock(
  transaction: TransactionClient,
  market: string,
): Promise<void> {
  await transaction.$executeRaw`
    SELECT pg_advisory_xact_lock(
      hashtextextended(${`vehicle-catalog:${market}`}, 0)
    )
  `;
}

@Injectable()
export class PrismaCatalogReleaseWorkflowRepository extends CatalogReleaseWorkflowRepository {
  constructor(private readonly prisma: PrismaService) {
    super();
  }

  approve(
    command: ApproveCatalogReleaseCommand,
  ): Promise<CatalogReleaseStateView> {
    return this.prisma.$transaction(
      async (transaction) => {
        const current = await findRelease(transaction, command.releaseId);
        if (current.revision !== command.expectedRevision) {
          throw new ReleaseConcurrencyError('catalog', command.releaseId);
        }
        await assertPublicationEligible(
          transaction,
          command.releaseId,
          command.now,
        );
        const patch = approveCatalogRelease(
          stateView(current),
          command.reviewerRef,
          command.evidenceRef,
          command.now,
        );
        const updated = await transaction.vehicleCatalogRelease.updateMany({
          data: {
            approvalEvidenceRef: patch.approvalEvidenceRef,
            approvedAt: patch.approvedAt,
            approvedByRef: patch.approvedByRef,
            revision: patch.revision,
            state: VehicleCatalogReleaseState.APPROVED,
          },
          where: {
            id: current.id,
            revision: current.revision,
            state: VehicleCatalogReleaseState.DRAFT,
          },
        });
        if (updated.count !== 1) {
          throw new ReleaseConcurrencyError('catalog', current.id);
        }
        await writeEvidence(transaction, {
          action: 'vehicle_catalog.release.approve',
          actorRef: command.reviewerRef,
          correlationId: command.correlationId,
          eventType: 'vehicle_catalog.release.approved',
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
    command: ActivateCatalogReleaseCommand,
  ): Promise<CatalogReleaseStateView> {
    return this.prisma.$transaction(
      async (transaction) => {
        const candidate = await findRelease(transaction, command.releaseId);
        await marketLock(transaction, candidate.market);
        const current = await findRelease(transaction, command.releaseId);
        if (current.revision !== command.expectedRevision) {
          throw new ReleaseConcurrencyError('catalog', command.releaseId);
        }
        await assertPublicationEligible(
          transaction,
          command.releaseId,
          command.now,
        );
        const activation = activateCatalogRelease(
          stateView(current),
          command.actorRef,
          command.now,
        );
        const active = await transaction.vehicleCatalogRelease.findFirst({
          select: releaseWorkflowSelection,
          where: {
            id: { not: current.id },
            market: current.market,
            state: VehicleCatalogReleaseState.ACTIVE,
          },
        });
        if (active !== null) {
          const supersession = supersedeCatalogRelease(
            stateView(active),
            command.now,
          );
          const result = await transaction.vehicleCatalogRelease.updateMany({
            data: {
              revision: supersession.revision,
              state: VehicleCatalogReleaseState.SUPERSEDED,
              supersededAt: supersession.supersededAt,
            },
            where: {
              id: active.id,
              revision: active.revision,
              state: VehicleCatalogReleaseState.ACTIVE,
            },
          });
          if (result.count !== 1) {
            throw new ReleaseConcurrencyError('catalog', active.id);
          }
        }
        const result = await transaction.vehicleCatalogRelease.updateMany({
          data: {
            activatedAt: activation.activatedAt,
            activatedByRef: activation.activatedByRef,
            revision: activation.revision,
            state: VehicleCatalogReleaseState.ACTIVE,
            supersededAt: null,
          },
          where: {
            id: current.id,
            revision: current.revision,
            state: VehicleCatalogReleaseState.APPROVED,
          },
        });
        if (result.count !== 1) {
          throw new ReleaseConcurrencyError('catalog', current.id);
        }
        await writeEvidence(transaction, {
          action: 'vehicle_catalog.release.activate',
          actorRef: command.actorRef,
          correlationId: command.correlationId,
          eventType: 'vehicle_catalog.release.activated',
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
    command: RollbackCatalogReleaseCommand,
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
          throw new ReleaseConcurrencyError('catalog', target.id);
        }
        await assertPublicationEligible(transaction, target.id, command.now);
        const current = await transaction.vehicleCatalogRelease.findFirst({
          select: releaseWorkflowSelection,
          where: {
            market: target.market,
            state: VehicleCatalogReleaseState.ACTIVE,
          },
        });
        if (current === null) {
          throw new ActiveReleaseNotFoundError('catalog', target.market);
        }
        if (current.revision !== command.expectedCurrentRevision) {
          throw new ReleaseConcurrencyError('catalog', current.id);
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
        const superseded = await transaction.vehicleCatalogRelease.updateMany({
          data: {
            revision: supersession.revision,
            state: VehicleCatalogReleaseState.SUPERSEDED,
            supersededAt: supersession.supersededAt,
          },
          where: {
            id: current.id,
            revision: current.revision,
            state: VehicleCatalogReleaseState.ACTIVE,
          },
        });
        if (superseded.count !== 1) {
          throw new ReleaseConcurrencyError('catalog', current.id);
        }
        const restored = await transaction.vehicleCatalogRelease.updateMany({
          data: {
            activatedAt: restoration.activatedAt,
            activatedByRef: restoration.activatedByRef,
            revision: restoration.revision,
            state: VehicleCatalogReleaseState.ACTIVE,
            supersededAt: null,
          },
          where: {
            id: target.id,
            revision: target.revision,
            state: VehicleCatalogReleaseState.SUPERSEDED,
          },
        });
        if (restored.count !== 1) {
          throw new ReleaseConcurrencyError('catalog', target.id);
        }
        await writeEvidence(transaction, {
          action: 'vehicle_catalog.release.rollback',
          actorRef: command.actorRef,
          correlationId: command.correlationId,
          eventType: 'vehicle_catalog.release.restored',
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
