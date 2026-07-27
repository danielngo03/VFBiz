import { createHash } from 'node:crypto';
import {
  BadRequestException,
  Body,
  ConflictException,
  Controller,
  ForbiddenException,
  Get,
  Headers,
  HttpException,
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
import { IdempotencyRepository } from '../application/ports/idempotency.repository';
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
const IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60;

function requireIdempotencyKey(
  value: string | undefined,
): asserts value is string {
  if (value === undefined || !IDEMPOTENCY_KEY_PATTERN.test(value)) {
    throw new BadRequestException({
      code: 'IDEMPOTENCY_KEY_REQUIRED',
      message: 'Idempotency-Key must contain 16 to 128 safe characters.',
    });
  }
}

function canonicalJson(value: unknown): string {
  if (
    value === null ||
    typeof value === 'boolean' ||
    typeof value === 'string' ||
    typeof value === 'number'
  ) {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(',')}]`;
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`)
      .join(',')}}`;
  }
  throw new BadRequestException({
    code: 'WORKFORCE_AUTHORIZATION_INVALID',
    message: 'Request body could not be canonicalized for idempotency.',
  });
}

export function idempotencyRequestHash(...parts: readonly unknown[]): string {
  return createHash('sha256').update(canonicalJson(parts)).digest('hex');
}

function toIdempotentHttpException(error: unknown): HttpException | null {
  if (error instanceof WorkforceAuthorizationNotFoundError) {
    return new NotFoundException({
      code: 'WORKFORCE_AUTHORIZATION_RESOURCE_NOT_FOUND',
      message: error.message,
    });
  }
  if (error instanceof WorkforceAuthorizationConflictError) {
    return new ConflictException({
      code: 'WORKFORCE_AUTHORIZATION_CONFLICT',
      message: error.message,
    });
  }
  if (error instanceof WorkforceAuthorizationForbiddenError) {
    return new ForbiddenException({
      code: 'WORKFORCE_AUTHORIZATION_FORBIDDEN',
      message: error.message,
    });
  }
  if (error instanceof WorkforceAuthorizationValidationError) {
    return new BadRequestException({
      code: 'WORKFORCE_AUTHORIZATION_INVALID',
      message: error.message,
    });
  }
  return null;
}

@Controller({ path: 'workforce', version: '1' })
@ApiExcludeController()
@RequireIdentityRealm('workforce')
export class WorkforceAuthorizationController {
  constructor(
    private readonly authorization: WorkforceAuthorizationService,
    private readonly idempotency: IdempotencyRepository,
  ) {}

  private async withIdempotency<T>(input: {
    namespace: string;
    idempotencyKey: string;
    requestHash: string;
    successStatus: number;
    operation: () => Promise<T>;
  }): Promise<T> {
    const reservation = await this.idempotency.reserve({
      namespace: input.namespace,
      key: input.idempotencyKey,
      requestHash: input.requestHash,
      ttlSeconds: IDEMPOTENCY_TTL_SECONDS,
    });
    if (reservation.kind === 'conflict') {
      throw new ConflictException({
        code: 'IDEMPOTENCY_KEY_CONFLICT',
        message:
          'This Idempotency-Key was already used for a different request, or the original request has not finished.',
      });
    }
    if (reservation.kind === 'replay') {
      if (reservation.responseStatus >= 400) {
        throw new HttpException(
          reservation.responseBody as Record<string, unknown>,
          reservation.responseStatus,
        );
      }
      return reservation.responseBody as T;
    }
    try {
      const result = await input.operation();
      await this.idempotency.complete({
        namespace: input.namespace,
        key: input.idempotencyKey,
        responseStatus: input.successStatus,
        responseBody: result,
      });
      return result;
    } catch (error) {
      const mapped = toIdempotentHttpException(error);
      if (mapped !== null) {
        await this.idempotency.complete({
          namespace: input.namespace,
          key: input.idempotencyKey,
          responseStatus: mapped.getStatus(),
          responseBody: mapped.getResponse(),
        });
        throw mapped;
      }
      // Unexpected error: do not cache it as if it were a legitimate
      // outcome. The pending record stays until it expires, so a corrected
      // retry with the same key can still succeed.
      throw error;
    }
  }

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
    return this.withIdempotency({
      namespace: 'workforce.role.create',
      idempotencyKey,
      requestHash: idempotencyRequestHash(principal.subject, body),
      successStatus: 201,
      operation: () =>
        this.authorization.createRole(principal, {
          ...body,
          correlationId: requestCorrelationId(request),
        }),
    });
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
    return this.withIdempotency({
      namespace: 'workforce.role.update',
      idempotencyKey,
      requestHash: idempotencyRequestHash(principal.subject, roleId, body),
      successStatus: 200,
      operation: () =>
        this.authorization.updateRole(principal, {
          ...body,
          correlationId: requestCorrelationId(request),
          roleId,
        }),
    });
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
    return this.withIdempotency({
      namespace: 'workforce.role.capabilities.replace',
      idempotencyKey,
      requestHash: idempotencyRequestHash(principal.subject, roleId, body),
      successStatus: 200,
      operation: () =>
        this.authorization.replaceRoleCapabilities(principal, {
          ...body,
          correlationId: requestCorrelationId(request),
          roleId,
        }),
    });
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
    return this.withIdempotency({
      namespace: 'workforce.assignment.create',
      idempotencyKey,
      requestHash: idempotencyRequestHash(principal.subject, body),
      successStatus: 201,
      operation: () =>
        this.authorization.createAssignment(principal, {
          ...body,
          correlationId: requestCorrelationId(request),
          effectiveAt: new Date(body.effectiveAt),
          expiresAt:
            body.expiresAt === undefined ? null : new Date(body.expiresAt),
        }),
    });
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
    return this.withIdempotency({
      namespace: 'workforce.assignment.revoke',
      idempotencyKey,
      requestHash: idempotencyRequestHash(
        principal.subject,
        assignmentId,
        body,
      ),
      successStatus: 201,
      operation: () =>
        this.authorization.revokeAssignment(principal, {
          ...body,
          assignmentId,
          correlationId: requestCorrelationId(request),
        }),
    });
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
    return this.withIdempotency({
      namespace: 'workforce.change-request.create',
      idempotencyKey,
      requestHash: idempotencyRequestHash(principal.subject, body),
      successStatus: 201,
      operation: () =>
        this.authorization.createChangeRequest(principal, {
          ...body,
          correlationId: requestCorrelationId(request),
        }),
    });
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
    return this.withIdempotency({
      namespace: 'workforce.change-request.approve',
      idempotencyKey,
      requestHash: idempotencyRequestHash(principal.subject, requestId, body),
      successStatus: 201,
      operation: () =>
        this.authorization.decideChangeRequest(principal, {
          ...body,
          correlationId: requestCorrelationId(request),
          decision: 'approved',
          reason: body.reason ?? null,
          requestId,
        }),
    });
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
    return this.withIdempotency({
      namespace: 'workforce.change-request.reject',
      idempotencyKey,
      requestHash: idempotencyRequestHash(principal.subject, requestId, body),
      successStatus: 201,
      operation: () =>
        this.authorization.decideChangeRequest(principal, {
          ...body,
          correlationId: requestCorrelationId(request),
          decision: 'rejected',
          reason: body.reason ?? null,
          requestId,
        }),
    });
  }
}
