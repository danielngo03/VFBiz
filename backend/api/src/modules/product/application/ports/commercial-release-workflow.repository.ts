import type { CatalogReleaseStateView } from '../../domain/catalog-release';

export interface ApproveCommercialReleaseCommand {
  readonly correlationId: string;
  readonly evidenceRef: string;
  readonly expectedRevision: number;
  readonly now: Date;
  readonly releaseId: string;
  readonly reviewerRef: string;
}

export interface ActivateCommercialReleaseCommand {
  readonly actorRef: string;
  readonly correlationId: string;
  readonly expectedRevision: number;
  readonly now: Date;
  readonly releaseId: string;
}

export interface RollbackCommercialReleaseCommand {
  readonly actorRef: string;
  readonly correlationId: string;
  readonly expectedCurrentRevision: number;
  readonly expectedTargetRevision: number;
  readonly now: Date;
  readonly targetReleaseId: string;
}

export abstract class CommercialReleaseWorkflowRepository {
  abstract approve(
    command: ApproveCommercialReleaseCommand,
  ): Promise<CatalogReleaseStateView>;

  abstract activate(
    command: ActivateCommercialReleaseCommand,
  ): Promise<CatalogReleaseStateView>;

  abstract rollback(
    command: RollbackCommercialReleaseCommand,
  ): Promise<CatalogReleaseStateView>;
}
