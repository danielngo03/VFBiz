import {
  Body,
  ConflictException,
  Controller,
  NotFoundException,
  Param,
  ParseUUIDPipe,
  Post,
  Req,
} from '@nestjs/common';
import { ApiExcludeController } from '@nestjs/swagger';
import type { AccessPrincipal } from '../../../platform/security/access-principal';
import { CurrentPrincipal } from '../../../platform/security/current-principal.decorator';
import { RequireAuthenticationMethods } from '../../../platform/security/required-authentication-methods';
import { RequireIdentityRealm } from '../../../platform/security/required-identity-realm';
import { RequireRoles } from '../../../platform/security/required-roles';
import {
  type RequestWithContext,
  requestCorrelationId,
} from '../../../platform/http/request-context';
import { CatalogReleaseWorkflowService } from '../application/services/catalog-release-workflow.service';
import { CommercialReleaseWorkflowService } from '../application/services/commercial-release-workflow.service';
import {
  ActiveReleaseNotFoundError,
  ReleaseConcurrencyError,
  ReleaseNotFoundError,
} from '../application/errors/release-workflow.errors';
import { CatalogReleaseTransitionError } from '../domain/catalog-release';
import {
  ActivateReleaseDto,
  ApproveReleaseDto,
  RollbackReleaseDto,
} from './dto/release-workflow.dto';

function mapReleaseError(error: unknown): never {
  if (
    error instanceof ReleaseNotFoundError ||
    error instanceof ActiveReleaseNotFoundError
  ) {
    throw new NotFoundException({
      code: 'RELEASE_NOT_FOUND',
      message: error.message,
    });
  }
  if (error instanceof ReleaseConcurrencyError) {
    throw new ConflictException({
      code: 'RELEASE_VERSION_CONFLICT',
      message: 'The release changed; reload it before trying again.',
    });
  }
  if (error instanceof CatalogReleaseTransitionError) {
    throw new ConflictException({ code: error.code, message: error.message });
  }
  throw error;
}

@Controller({ path: 'operations/releases', version: '1' })
@ApiExcludeController()
@RequireIdentityRealm('workforce')
@RequireAuthenticationMethods(['otp'])
export class OperationsReleaseController {
  constructor(
    private readonly catalog: CatalogReleaseWorkflowService,
    private readonly commercial: CommercialReleaseWorkflowService,
  ) {}

  @Post('vehicle-catalog/:releaseId/approve')
  @RequireRoles({ mode: 'all-of', roles: ['vehicle-data-reviewer'] })
  async approveCatalog(
    @Param('releaseId', ParseUUIDPipe) releaseId: string,
    @Body() body: ApproveReleaseDto,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Req() request: RequestWithContext,
  ) {
    try {
      return await this.catalog.approve({
        correlationId: requestCorrelationId(request),
        evidenceRef: body.evidenceRef,
        expectedRevision: body.expectedRevision,
        now: new Date(),
        releaseId,
        reviewerRef: principal.subject,
      });
    } catch (error) {
      return mapReleaseError(error);
    }
  }

  @Post('vehicle-catalog/:releaseId/activate')
  @RequireRoles({ mode: 'all-of', roles: ['vehicle-data-operator'] })
  async activateCatalog(
    @Param('releaseId', ParseUUIDPipe) releaseId: string,
    @Body() body: ActivateReleaseDto,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Req() request: RequestWithContext,
  ) {
    try {
      return await this.catalog.activate({
        actorRef: principal.subject,
        correlationId: requestCorrelationId(request),
        expectedRevision: body.expectedRevision,
        now: new Date(),
        releaseId,
      });
    } catch (error) {
      return mapReleaseError(error);
    }
  }

  @Post('vehicle-catalog/:releaseId/rollback')
  @RequireRoles({ mode: 'all-of', roles: ['vehicle-data-operator'] })
  async rollbackCatalog(
    @Param('releaseId', ParseUUIDPipe) targetReleaseId: string,
    @Body() body: RollbackReleaseDto,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Req() request: RequestWithContext,
  ) {
    try {
      return await this.catalog.rollback({
        actorRef: principal.subject,
        correlationId: requestCorrelationId(request),
        expectedCurrentRevision: body.expectedCurrentRevision,
        expectedTargetRevision: body.expectedTargetRevision,
        now: new Date(),
        targetReleaseId,
      });
    } catch (error) {
      return mapReleaseError(error);
    }
  }

  @Post('commercial/:releaseId/approve')
  @RequireRoles({ mode: 'all-of', roles: ['commercial-data-reviewer'] })
  async approveCommercial(
    @Param('releaseId', ParseUUIDPipe) releaseId: string,
    @Body() body: ApproveReleaseDto,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Req() request: RequestWithContext,
  ) {
    try {
      return await this.commercial.approve({
        correlationId: requestCorrelationId(request),
        evidenceRef: body.evidenceRef,
        expectedRevision: body.expectedRevision,
        now: new Date(),
        releaseId,
        reviewerRef: principal.subject,
      });
    } catch (error) {
      return mapReleaseError(error);
    }
  }

  @Post('commercial/:releaseId/activate')
  @RequireRoles({ mode: 'all-of', roles: ['commercial-data-operator'] })
  async activateCommercial(
    @Param('releaseId', ParseUUIDPipe) releaseId: string,
    @Body() body: ActivateReleaseDto,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Req() request: RequestWithContext,
  ) {
    try {
      return await this.commercial.activate({
        actorRef: principal.subject,
        correlationId: requestCorrelationId(request),
        expectedRevision: body.expectedRevision,
        now: new Date(),
        releaseId,
      });
    } catch (error) {
      return mapReleaseError(error);
    }
  }

  @Post('commercial/:releaseId/rollback')
  @RequireRoles({ mode: 'all-of', roles: ['commercial-data-operator'] })
  async rollbackCommercial(
    @Param('releaseId', ParseUUIDPipe) targetReleaseId: string,
    @Body() body: RollbackReleaseDto,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Req() request: RequestWithContext,
  ) {
    try {
      return await this.commercial.rollback({
        actorRef: principal.subject,
        correlationId: requestCorrelationId(request),
        expectedCurrentRevision: body.expectedCurrentRevision,
        expectedTargetRevision: body.expectedTargetRevision,
        now: new Date(),
        targetReleaseId,
      });
    } catch (error) {
      return mapReleaseError(error);
    }
  }
}
