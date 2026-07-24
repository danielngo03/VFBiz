import {
  BadRequestException,
  Body,
  ConflictException,
  Controller,
  Delete,
  Get,
  Headers,
  NotFoundException,
  Param,
  ParseUUIDPipe,
  Patch,
  Post,
  Req,
  Res,
  ServiceUnavailableException,
} from '@nestjs/common';
import {
  ApiBadRequestResponse,
  ApiConflictResponse,
  ApiCreatedResponse,
  ApiForbiddenResponse,
  ApiNotFoundResponse,
  ApiOkResponse,
  ApiOperation,
  ApiParam,
  ApiServiceUnavailableResponse,
  ApiTags,
  ApiUnauthorizedResponse,
} from '@nestjs/swagger';
import type { FastifyReply } from 'fastify';
import type { AccessPrincipal } from '../../../platform/security/access-principal';
import {
  type RequestWithContext,
  requestCorrelationId,
} from '../../../platform/http/request-context';
import { RequireIdentityRealm } from '../../../platform/security/required-identity-realm';
import { RequireScopes } from '../../../platform/security/required-scopes';
import { CustomerGarageService } from '../application/services/customer-garage.service';
import {
  CustomerGarageEntryNotFoundError,
  CustomerGarageConcurrentModificationError,
  CustomerGarageIdempotencyConflictError,
  CustomerGaragePrimaryInvariantError,
  CustomerGarageVariantUnavailableError,
  CustomerGarageVersionConflictError,
  type CustomerGarageEntryView,
} from '../domain/customer-garage';
import { CurrentPrincipal } from './current-principal.decorator';
import {
  CUSTOMER_AUTHORIZED_PARTIES,
  CUSTOMER_OPERATION_SCOPES,
} from './customer-scope-policy';
import {
  CreateCustomerGarageEntryDto,
  UpdateCustomerGarageEntryDto,
} from './dto/customer-garage.dto';

const IDEMPOTENCY_KEY_PATTERN = /^[A-Za-z0-9._~:+\-/]{16,128}$/;
const GARAGE_ETAG_PATTERN = /^(?:W\/)?"garage-(\d+)"$/;

function garageEtag(version: number): string {
  return `"garage-${version}"`;
}

function expectedGarageVersion(ifMatch: string | undefined): number {
  const match = ifMatch?.match(GARAGE_ETAG_PATTERN);
  if (match === undefined || match === null) {
    throw new BadRequestException({
      code: 'GARAGE_IF_MATCH_REQUIRED',
      message: 'If-Match must contain the current garage entry ETag.',
    });
  }
  return Number(match[1]);
}

function assertGaragePatchHasChange(body: UpdateCustomerGarageEntryDto): void {
  if (body.isPrimary === undefined && body.nickname === undefined) {
    throw new BadRequestException({
      code: 'GARAGE_PATCH_EMPTY',
      message: 'At least one garage field must be provided.',
    });
  }
}

function checkedIdempotencyKey(value: string | undefined): string {
  if (value === undefined || !IDEMPOTENCY_KEY_PATTERN.test(value)) {
    throw new BadRequestException({
      code: 'IDEMPOTENCY_KEY_REQUIRED',
      message: 'Idempotency-Key must contain 16 to 128 safe characters.',
    });
  }
  return value;
}

function mapGarageError(error: unknown): never {
  if (error instanceof CustomerGarageEntryNotFoundError) {
    throw new NotFoundException({
      code: 'GARAGE_ENTRY_NOT_FOUND',
      message: 'The garage entry was not found.',
    });
  }
  if (
    error instanceof CustomerGarageVersionConflictError ||
    error instanceof CustomerGarageConcurrentModificationError ||
    error instanceof CustomerGarageIdempotencyConflictError ||
    error instanceof CustomerGaragePrimaryInvariantError
  ) {
    throw new ConflictException({
      code: error.name
        .replaceAll(/([a-z])([A-Z])/g, '$1_$2')
        .toUpperCase()
        .replace('_ERROR', ''),
      message: error.message,
    });
  }
  if (error instanceof CustomerGarageVariantUnavailableError) {
    throw new ServiceUnavailableException({
      code: 'GARAGE_VARIANT_UNAVAILABLE',
      message: 'The selected variant is unavailable in the active catalog.',
    });
  }
  throw error;
}

@Controller({ path: 'me/vehicles', version: '1' })
@RequireIdentityRealm('customer')
@ApiTags('Garage')
export class CustomerGarageController {
  constructor(private readonly garage: CustomerGarageService) {}

  @Get()
  @ApiOperation({
    operationId: 'listMyVehicles',
    summary: 'List garage',
    description:
      'Lists active self-reported vehicles for the current customer subject only.',
  })
  @ApiOkResponse({ description: 'Customer garage entries.' })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({ description: 'Missing garage read scope.' })
  @RequireScopes({
    allowedAuthorizedParties: CUSTOMER_AUTHORIZED_PARTIES,
    mode: 'all-of',
    scopes: [CUSTOMER_OPERATION_SCOPES.garageRead],
  })
  list(@CurrentPrincipal() principal: AccessPrincipal) {
    return this.garage.list(principal);
  }

  @Post()
  @ApiOperation({
    operationId: 'createMyVehicle',
    summary: 'Add a vehicle',
    description:
      'Adds one self-reported vehicle variant. Ownership status remains `unverified` until a trusted provider confirms it.',
  })
  @ApiCreatedResponse({ description: 'Unverified garage entry created.' })
  @ApiBadRequestResponse({
    description: 'Invalid request body or idempotency key.',
  })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({
    description: 'Missing garage write scope or CSRF token.',
  })
  @ApiConflictResponse({
    description: 'Idempotency, version or primary-vehicle invariant conflict.',
  })
  @ApiServiceUnavailableResponse({
    description: 'The selected vehicle variant is not available.',
  })
  @RequireScopes({
    allowedAuthorizedParties: CUSTOMER_AUTHORIZED_PARTIES,
    mode: 'all-of',
    scopes: [CUSTOMER_OPERATION_SCOPES.garageWrite],
  })
  async create(
    @Body() body: CreateCustomerGarageEntryDto,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Headers('idempotency-key') idempotencyKey: string | undefined,
    @Req() request: RequestWithContext,
    @Res({ passthrough: true }) reply: FastifyReply,
  ): Promise<CustomerGarageEntryView> {
    try {
      const entry = await this.garage.create(
        principal,
        requestCorrelationId(request),
        checkedIdempotencyKey(idempotencyKey),
        body,
      );
      void reply.header('etag', garageEtag(entry.version));
      return entry;
    } catch (error) {
      return mapGarageError(error);
    }
  }

  @Patch(':entryId')
  @ApiOperation({
    operationId: 'updateMyVehicle',
    summary: 'Update vehicle',
    description:
      'Updates one garage entry using optimistic concurrency through `If-Match`.',
  })
  @ApiParam({ format: 'uuid', name: 'entryId' })
  @ApiOkResponse({ description: 'Updated garage entry.' })
  @ApiBadRequestResponse({
    description: '`If-Match` or request body is invalid.',
  })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({
    description: 'Missing garage write scope or CSRF token.',
  })
  @ApiNotFoundResponse({
    description: 'Garage entry not found for this subject.',
  })
  @ApiConflictResponse({
    description: 'Version or primary-vehicle invariant conflict.',
  })
  @ApiServiceUnavailableResponse({
    description: 'The selected vehicle variant is not available.',
  })
  @RequireScopes({
    allowedAuthorizedParties: CUSTOMER_AUTHORIZED_PARTIES,
    mode: 'all-of',
    scopes: [CUSTOMER_OPERATION_SCOPES.garageWrite],
  })
  async update(
    @Param('entryId', new ParseUUIDPipe({ version: '4' })) entryId: string,
    @Body() body: UpdateCustomerGarageEntryDto,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Headers('if-match') ifMatch: string | undefined,
    @Req() request: RequestWithContext,
    @Res({ passthrough: true }) reply: FastifyReply,
  ): Promise<CustomerGarageEntryView> {
    try {
      assertGaragePatchHasChange(body);
      const entry = await this.garage.update(
        principal,
        requestCorrelationId(request),
        entryId,
        expectedGarageVersion(ifMatch),
        body,
      );
      void reply.header('etag', garageEtag(entry.version));
      return entry;
    } catch (error) {
      return mapGarageError(error);
    }
  }

  @Delete(':entryId')
  @ApiOperation({
    operationId: 'deleteMyVehicle',
    summary: 'Archive vehicle',
    description:
      'Archives one garage entry. The entry is hidden from active garage views but remains auditable.',
  })
  @ApiParam({ format: 'uuid', name: 'entryId' })
  @ApiOkResponse({ description: 'Archived garage entry.' })
  @ApiBadRequestResponse({ description: '`If-Match` is missing or invalid.' })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({
    description: 'Missing garage write scope or CSRF token.',
  })
  @ApiNotFoundResponse({
    description: 'Garage entry not found for this subject.',
  })
  @ApiConflictResponse({ description: 'Version conflict.' })
  @RequireScopes({
    allowedAuthorizedParties: CUSTOMER_AUTHORIZED_PARTIES,
    mode: 'all-of',
    scopes: [CUSTOMER_OPERATION_SCOPES.garageWrite],
  })
  async archive(
    @Param('entryId', new ParseUUIDPipe({ version: '4' })) entryId: string,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Headers('if-match') ifMatch: string | undefined,
    @Req() request: RequestWithContext,
    @Res({ passthrough: true }) reply: FastifyReply,
  ): Promise<CustomerGarageEntryView> {
    try {
      const entry = await this.garage.archive(
        principal,
        requestCorrelationId(request),
        entryId,
        expectedGarageVersion(ifMatch),
      );
      void reply.header('etag', garageEtag(entry.version));
      return entry;
    } catch (error) {
      return mapGarageError(error);
    }
  }
}
