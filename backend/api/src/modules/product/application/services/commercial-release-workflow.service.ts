import { Injectable } from '@nestjs/common';
import type { CatalogReleaseStateView } from '../../domain/catalog-release';
import {
  CommercialReleaseWorkflowRepository,
  type ActivateCommercialReleaseCommand,
  type ApproveCommercialReleaseCommand,
  type RollbackCommercialReleaseCommand,
} from '../ports/commercial-release-workflow.repository';

@Injectable()
export class CommercialReleaseWorkflowService {
  constructor(
    private readonly repository: CommercialReleaseWorkflowRepository,
  ) {}

  approve(
    command: ApproveCommercialReleaseCommand,
  ): Promise<CatalogReleaseStateView> {
    return this.repository.approve(command);
  }

  activate(
    command: ActivateCommercialReleaseCommand,
  ): Promise<CatalogReleaseStateView> {
    return this.repository.activate(command);
  }

  rollback(
    command: RollbackCommercialReleaseCommand,
  ): Promise<CatalogReleaseStateView> {
    return this.repository.rollback(command);
  }
}
