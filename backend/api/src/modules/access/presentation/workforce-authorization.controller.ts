import {
  BadRequestException,
  Body,
  ConflictException,
  Controller,
  ForbiddenException,
  Get,
  Headers,
  NotFoundException,
  Param,
  ParseUUIDPipe,
  Patch,
  Post,
  Put,
  Req,
} from '@nestjs/common';
import { ApiExcludeController } from '@nestjs/swagger';
import type { AccessPrincipal } from '../../../platform/security/access-principal';
import { CurrentPrincipal } from '../../../platform/security/current-principal.decorator';
import { RequireCapabilities } from '../../../platform/security/required-capabilities';
import { RequireIdentityRealm } from '../../../platform/security/required-identity-realm';
import {
  type RequestWithContext,
  requestCorrelationId,
} from '../../../platform/http/request-context';
import {
  WorkforceAuthorizationConflictError,
  WorkforceAuthorizationForbiddenError,
  WorkforceAuthorizationNotFoundError,
  WorkforceAuthorizationValidationError,
} from '../application/errors/workforce-authorization.errors';
import { WorkforceAuthorizationService } from '../application/services/workforce-authorization.service';
import {
  CreateAuthorizationChangeRequestDto,
  CreateWorkforceAssignmentDto,
  CreateWorkforceRoleDto,
  DecideAuthorizationChangeRequestDto,
  ReplaceRoleCapabilitiesDto,
  UpdateWorkforceRoleDto,
  VersionedMutationDto,
} from './workforce-authorization.dto';

const IDEMPOTENCY_KEY_PATTERN = /^[A-Za-z0-9._~:+\-/]{16,128}$/;

function requireIdempotencyKey(value: string | undefined): void {
  if (value === undefined || !IDEMPOTENCY_KEY_PATTERN.test(value)) {
    throw new BadRequestException({
      code: 'IDEMPOTENCY_KEY_REQUIRED',
      message: 'Idempotency-Key must contain 16 to 128 safe characters.',
    });
  }
}

function mapAuthorizationError(error: unknown): never {
  if (error instanceof WorkforceAuthorizationNotFoundError) {
    throw new NotFoundException({
      code: 'WORKFORCE_AUTHORIZATION_RESOURCE_NOT_FOUND',
      message: error.message,
    });
  }
  if (error instanceof WorkforceAuthorizationConflictError) {
    throw new ConflictException({
      code: 'WORKFORCE_AUTHORIZATION_CONFLICT',
      message: error.message,
    });
  }
  if (error instanceof WorkforceAuthorizationForbiddenError) {
    throw new ForbiddenException({
      code: 'WORKFORCE_AUTHORIZATION_FORBIDDEN',
      message: error.message,
    });
  }
  if (error instanceof WorkforceAuthorizationValidationError) {
    throw new BadRequestException({
      code: 'WORKFORCE_AUTHORIZATION_INVALID',
      message: error.message,
    });
  }
  throw error;
}

@Controller({ path: 'workforce', version: '1' })
@ApiExcludeController()
@RequireIdentityRealm('workforce')
export class WorkforceAuthorizationController {
  constructor(private readonly authorization: WorkforceAuthorizationService) {}

  @Get('me/entitlements')
  async entitlements(@CurrentPrincipal() principal: AccessPrincipal) {
    const result = await this.authorization.entitlements(principal);
    if (result === null) {
      throw new ForbiddenException({
        code: 'WORKFORCE_IDENTITY_NOT_REGISTERED',
        message: 'The workforce identity is not registered locally.',
      });
    }
    return result;
  }

  @Get('authorization/capabilities')
  @RequireCapabilities({
    mode: 'all-of',
    capabilities: ['authorization.role.read'],
  })
  capabilities() {
    return this.authorization.capabilities();
  }

  @Get('authorization/roles')
  @RequireCapabilities({
    mode: 'all-of',
    capabilities: ['authorization.role.read'],
  })
  roles() {
    return this.authorization.roles();
  }

  @Get('authorization/roles/:roleId')
  @RequireCapabilities({
    mode: 'all-of',
    capabilities: ['authorization.role.read'],
  })
  async role(@Param('roleId', ParseUUIDPipe) roleId: string) {
    const role = await this.authorization.role(roleId);
    if (role === null) {
      throw new NotFoundException({
        code: 'WORKFORCE_ROLE_NOT_FOUND',
        message: 'The workforce role was not found.',
      });
    }
    return role;
  }

  @Post('authorization/roles')
  @RequireCapabilities({
    mode: 'all-of',
    capabilities: ['authorization.role.create'],
  })
  async createRole(
    @Body() body: CreateWorkforceRoleDto,
    @Headers('idempotency-key') idempotencyKey: string | undefined,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Req() request: RequestWithContext,
  ) {
    requireIdempotencyKey(idempotencyKey);
    try {
      return await this.authorization.createRole(principal, {
        ...body,
        correlationId: requestCorrelationId(request),
      });
    } catch (error) {
      return mapAuthorizationError(error);
    }
  }

  @Patch('authorization/roles/:roleId')
  @RequireCapabilities({
    mode: 'all-of',
    capabilities: ['authorization.role.update'],
  })
  async updateRole(
    @Param('roleId', ParseUUIDPipe) roleId: string,
    @Body() body: UpdateWorkforceRoleDto,
    @Headers('idempotency-key') idempotencyKey: string | undefined,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Req() request: RequestWithContext,
  ) {
    requireIdempotencyKey(idempotencyKey);
    try {
      return await this.authorization.updateRole(principal, {
        ...body,
        correlationId: requestCorrelationId(request),
        roleId,
      });
    } catch (error) {
      return mapAuthorizationError(error);
    }
  }

  @Put('authorization/roles/:roleId/capabilities')
  @RequireCapabilities({
    mode: 'all-of',
    capabilities: ['authorization.role.update'],
  })
  async replaceCapabilities(
    @Param('roleId', ParseUUIDPipe) roleId: string,
    @Body() body: ReplaceRoleCapabilitiesDto,
    @Headers('idempotency-key') idempotencyKey: string | undefined,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Req() request: RequestWithContext,
  ) {
    requireIdempotencyKey(idempotencyKey);
    try {
      return await this.authorization.replaceRoleCapabilities(principal, {
        ...body,
        correlationId: requestCorrelationId(request),
        roleId,
      });
    } catch (error) {
      return mapAuthorizationError(error);
    }
  }

  @Get('authorization/assignments')
  @RequireCapabilities({
    mode: 'all-of',
    capabilities: ['authorization.assignment.read'],
  })
  assignments() {
    return this.authorization.assignments();
  }

  @Post('authorization/assignments')
  @RequireCapabilities({
    mode: 'all-of',
    capabilities: ['authorization.assignment.create'],
  })
  async createAssignment(
    @Body() body: CreateWorkforceAssignmentDto,
    @Headers('idempotency-key') idempotencyKey: string | undefined,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Req() request: RequestWithContext,
  ) {
    requireIdempotencyKey(idempotencyKey);
    try {
      return await this.authorization.createAssignment(principal, {
        ...body,
        correlationId: requestCorrelationId(request),
        effectiveAt: new Date(body.effectiveAt),
        expiresAt:
          body.expiresAt === undefined ? null : new Date(body.expiresAt),
      });
    } catch (error) {
      return mapAuthorizationError(error);
    }
  }

  @Post('authorization/assignments/:assignmentId/revoke')
  @RequireCapabilities({
    mode: 'all-of',
    capabilities: ['authorization.assignment.revoke'],
  })
  async revokeAssignment(
    @Param('assignmentId', ParseUUIDPipe) assignmentId: string,
    @Body() body: VersionedMutationDto,
    @Headers('idempotency-key') idempotencyKey: string | undefined,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Req() request: RequestWithContext,
  ) {
    requireIdempotencyKey(idempotencyKey);
    try {
      return await this.authorization.revokeAssignment(principal, {
        ...body,
        assignmentId,
        correlationId: requestCorrelationId(request),
      });
    } catch (error) {
      return mapAuthorizationError(error);
    }
  }

  @Get('authorization/change-requests')
  @RequireCapabilities({
    mode: 'all-of',
    capabilities: ['authorization.approval.read'],
  })
  changeRequests() {
    return this.authorization.changeRequests();
  }

  @Get('directory/subjects')
  @RequireCapabilities({
    mode: 'all-of',
    capabilities: ['authorization.assignment.read'],
  })
  directorySubjects() {
    return this.authorization.directorySubjects();
  }

  @Get('directory/organization-units')
  @RequireCapabilities({
    mode: 'all-of',
    capabilities: ['authorization.assignment.read'],
  })
  organizationUnits() {
    return this.authorization.organizationUnits();
  }

  @Get('audit-events')
  @RequireCapabilities({
    mode: 'all-of',
    capabilities: ['audit.event.read'],
  })
  auditEvents() {
    return this.authorization.auditEvents();
  }

  @Post('authorization/change-requests')
  @RequireCapabilities({
    mode: 'any-of',
    capabilities: [
      'authorization.role.update',
      'authorization.role.disable',
      'authorization.assignment.create',
    ],
  })
  async createChangeRequest(
    @Body() body: CreateAuthorizationChangeRequestDto,
    @Headers('idempotency-key') idempotencyKey: string | undefined,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Req() request: RequestWithContext,
  ) {
    requireIdempotencyKey(idempotencyKey);
    try {
      return await this.authorization.createChangeRequest(principal, {
        ...body,
        correlationId: requestCorrelationId(request),
      });
    } catch (error) {
      return mapAuthorizationError(error);
    }
  }

  @Post('authorization/change-requests/:requestId/approve')
  @RequireCapabilities({
    mode: 'all-of',
    capabilities: ['authorization.approval.approve'],
  })
  async approveChangeRequest(
    @Param('requestId', ParseUUIDPipe) requestId: string,
    @Body() body: DecideAuthorizationChangeRequestDto,
    @Headers('idempotency-key') idempotencyKey: string | undefined,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Req() request: RequestWithContext,
  ) {
    requireIdempotencyKey(idempotencyKey);
    try {
      return await this.authorization.decideChangeRequest(principal, {
        ...body,
        correlationId: requestCorrelationId(request),
        decision: 'approved',
        reason: body.reason ?? null,
        requestId,
      });
    } catch (error) {
      return mapAuthorizationError(error);
    }
  }

  @Post('authorization/change-requests/:requestId/reject')
  @RequireCapabilities({
    mode: 'all-of',
    capabilities: ['authorization.approval.reject'],
  })
  async rejectChangeRequest(
    @Param('requestId', ParseUUIDPipe) requestId: string,
    @Body() body: DecideAuthorizationChangeRequestDto,
    @Headers('idempotency-key') idempotencyKey: string | undefined,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Req() request: RequestWithContext,
  ) {
    requireIdempotencyKey(idempotencyKey);
    try {
      return await this.authorization.decideChangeRequest(principal, {
        ...body,
        correlationId: requestCorrelationId(request),
        decision: 'rejected',
        reason: body.reason ?? null,
        requestId,
      });
    } catch (error) {
      return mapAuthorizationError(error);
    }
  }
}
