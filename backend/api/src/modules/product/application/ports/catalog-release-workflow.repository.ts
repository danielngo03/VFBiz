import type { CatalogReleaseStateView } from '../../domain/catalog-release';

export interface ApproveCatalogReleaseCommand {
  readonly correlationId: string;
  readonly evidenceRef: string;
  readonly expectedRevision: number;
  readonly now: Date;
  readonly releaseId: string;
  readonly reviewerRef: string;
}

export interface ActivateCatalogReleaseCommand {
  readonly actorRef: string;
  readonly correlationId: string;
  readonly expectedRevision: number;
  readonly now: Date;
  readonly releaseId: string;
}

export interface RollbackCatalogReleaseCommand {
  readonly actorRef: string;
  readonly correlationId: string;
  readonly expectedCurrentRevision: number;
  readonly expectedTargetRevision: number;
  readonly now: Date;
  readonly targetReleaseId: string;
}

export abstract class CatalogReleaseWorkflowRepository {
  abstract approve(
    command: ApproveCatalogReleaseCommand,
  ): Promise<CatalogReleaseStateView>;

  abstract activate(
    command: ActivateCatalogReleaseCommand,
  ): Promise<CatalogReleaseStateView>;

  abstract rollback(
    command: RollbackCatalogReleaseCommand,
  ): Promise<CatalogReleaseStateView>;
}
