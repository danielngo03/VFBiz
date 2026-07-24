import { Injectable } from '@nestjs/common';
import {
  CatalogReleaseWorkflowRepository,
  type ActivateCatalogReleaseCommand,
  type ApproveCatalogReleaseCommand,
  type RollbackCatalogReleaseCommand,
} from '../ports/catalog-release-workflow.repository';
import type { CatalogReleaseStateView } from '../../domain/catalog-release';

@Injectable()
export class CatalogReleaseWorkflowService {
  constructor(private readonly repository: CatalogReleaseWorkflowRepository) {}

  approve(
    command: ApproveCatalogReleaseCommand,
  ): Promise<CatalogReleaseStateView> {
    return this.repository.approve(command);
  }

  activate(
    command: ActivateCatalogReleaseCommand,
  ): Promise<CatalogReleaseStateView> {
    return this.repository.activate(command);
  }

  rollback(
    command: RollbackCatalogReleaseCommand,
  ): Promise<CatalogReleaseStateView> {
    return this.repository.rollback(command);
  }
}
