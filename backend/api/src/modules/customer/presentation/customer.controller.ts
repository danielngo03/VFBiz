import {
  BadRequestException,
  Body,
  ConflictException,
  Controller,
  Get,
  Headers,
  HttpCode,
  HttpStatus,
  NotFoundException,
  Param,
  ParseUUIDPipe,
  Patch,
  Post,
  Put,
  Req,
  Res,
} from '@nestjs/common';
import {
  ApiAcceptedResponse,
  ApiBadRequestResponse,
  ApiConflictResponse,
  ApiForbiddenResponse,
  ApiNotFoundResponse,
  ApiOkResponse,
  ApiOperation,
  ApiTags,
  ApiUnauthorizedResponse,
} from '@nestjs/swagger';
import type { FastifyReply } from 'fastify';
import type { AccessPrincipal } from '../../../platform/security/access-principal';
import { RequireIdentityRealm } from '../../../platform/security/required-identity-realm';
import { RequireScopes } from '../../../platform/security/required-scopes';
import {
  type RequestWithContext,
  requestCorrelationId,
} from '../../../platform/http/request-context';
import { CustomerAccountService } from '../application/services/customer-account.service';
import {
  CustomerConsentBatchValidationError,
  CustomerConsentPolicyUnavailableError,
  CustomerDataRequestNotFoundError,
  CustomerIdempotencyConflictError,
  CustomerProfileUnavailableError,
  CustomerProfileVersionConflictError,
  type CustomerProfileView,
} from '../domain/customer-account';
import { CurrentPrincipal } from './current-principal.decorator';
import {
  CUSTOMER_AUTHORIZED_PARTIES,
  CUSTOMER_OPERATION_SCOPES,
} from './customer-scope-policy';
import {
  CreateCustomerDataRequestDto,
  CustomerDataRequestResponseDto,
  UpdateConsentsDto,
  UpdateCustomerProfileDto,
} from './dto/customer-account.dto';

const IDEMPOTENCY_KEY_PATTERN = /^[A-Za-z0-9._~:+\-/]{16,128}$/;
const PROFILE_ETAG_PATTERN = /^(?:W\/)?"profile-(\d+)"$/;

function profileEtag(version: number): string {
  return `"profile-${version}"`;
}

function expectedProfileVersion(ifMatch: string | undefined): number {
  const match = ifMatch?.match(PROFILE_ETAG_PATTERN);
  if (match === undefined || match === null) {
    throw new BadRequestException({
      code: 'PROFILE_IF_MATCH_REQUIRED',
      message: 'If-Match must contain the current profile ETag.',
    });
  }
  return Number(match[1]);
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

function assertProfilePatchHasChange(body: UpdateCustomerProfileDto): void {
  const preferenceChange =
    body.communicationPreferences !== undefined &&
    Object.values(body.communicationPreferences).some(
      (value) => value !== undefined,
    );
  if (
    body.displayName === undefined &&
    body.locale === undefined &&
    body.market === undefined &&
    body.timezone === undefined &&
    !preferenceChange
  ) {
    throw new BadRequestException({
      code: 'PROFILE_PATCH_EMPTY',
      message: 'At least one profile field must be provided.',
    });
  }
}

function mapCustomerError(error: unknown): never {
  if (error instanceof CustomerConsentBatchValidationError) {
    throw new BadRequestException({
      code: 'CONSENT_BATCH_INVALID',
      message: 'A consent purpose may appear only once in a request.',
    });
  }
  if (error instanceof CustomerConsentPolicyUnavailableError) {
    throw new ConflictException({
      code: 'CONSENT_POLICY_UNAVAILABLE',
      message: 'The requested consent policy is not active.',
    });
  }
  if (error instanceof CustomerProfileVersionConflictError) {
    throw new ConflictException({
      code: 'PROFILE_VERSION_CONFLICT',
      message: 'The profile changed; reload it before trying again.',
    });
  }
  if (error instanceof CustomerIdempotencyConflictError) {
    throw new ConflictException({
      code: 'IDEMPOTENCY_KEY_REUSED',
      message: 'The idempotency key was used for another request.',
    });
  }
  if (error instanceof CustomerProfileUnavailableError) {
    throw new ConflictException({
      code: 'CUSTOMER_PROFILE_UNAVAILABLE',
      message: 'The customer profile is unavailable.',
    });
  }
  throw error;
}

@Controller({ path: 'me', version: '1' })
@RequireIdentityRealm('customer')
@ApiTags('Customer')
export class CustomerController {
  constructor(private readonly accounts: CustomerAccountService) {}

  @Get()
  @ApiOperation({
    operationId: 'getMyProfile',
    summary: 'Get profile',
    description:
      'Return the customer profile attached to the verified OIDC subject.',
  })
  @ApiOkResponse({ description: 'Current customer profile.' })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({ description: 'Missing profile read scope.' })
  @RequireScopes({
    allowedAuthorizedParties: CUSTOMER_AUTHORIZED_PARTIES,
    mode: 'all-of',
    scopes: [CUSTOMER_OPERATION_SCOPES.profileRead],
  })
  async getProfile(
    @CurrentPrincipal() principal: AccessPrincipal,
    @Res({ passthrough: true }) reply: FastifyReply,
  ): Promise<CustomerProfileView> {
    try {
      const profile = await this.accounts.getProfile(principal);
      void reply.header('etag', profileEtag(profile.version));
      return profile;
    } catch (error) {
      return mapCustomerError(error);
    }
  }

  @Patch()
  @ApiOperation({
    operationId: 'updateMyProfile',
    summary: 'Update profile',
    description:
      'Update customer preferences with optimistic concurrency through `If-Match`.',
  })
  @ApiOkResponse({ description: 'Updated customer profile.' })
  @ApiBadRequestResponse({
    description: '`If-Match` or request body is invalid.',
  })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({
    description: 'Missing profile write scope or CSRF token.',
  })
  @ApiConflictResponse({ description: 'Profile version conflict.' })
  @RequireScopes({
    allowedAuthorizedParties: CUSTOMER_AUTHORIZED_PARTIES,
    mode: 'all-of',
    scopes: [CUSTOMER_OPERATION_SCOPES.profileWrite],
  })
  async updateProfile(
    @Body() body: UpdateCustomerProfileDto,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Headers('if-match') ifMatch: string | undefined,
    @Req() request: RequestWithContext,
    @Res({ passthrough: true }) reply: FastifyReply,
  ): Promise<CustomerProfileView> {
    try {
      assertProfilePatchHasChange(body);
      const profile = await this.accounts.updateProfile(
        principal,
        requestCorrelationId(request),
        expectedProfileVersion(ifMatch),
        body,
      );
      void reply.header('etag', profileEtag(profile.version));
      return profile;
    } catch (error) {
      return mapCustomerError(error);
    }
  }

  @Get('consents')
  @ApiOperation({
    operationId: 'listMyConsents',
    summary: 'List consents',
    description:
      'Return current consent state by purpose without exposing ledger internals.',
  })
  @ApiOkResponse({ description: 'Current consent state.' })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({ description: 'Missing consent read scope.' })
  @RequireScopes({
    allowedAuthorizedParties: CUSTOMER_AUTHORIZED_PARTIES,
    mode: 'all-of',
    scopes: [CUSTOMER_OPERATION_SCOPES.consentRead],
  })
  listConsents(@CurrentPrincipal() principal: AccessPrincipal) {
    return this.accounts.listConsents(principal);
  }

  @Put('consents')
  @ApiOperation({
    operationId: 'putMyConsent',
    summary: 'Update consents',
    description:
      'Record an immutable consent batch. Duplicate purposes or idempotency conflicts fail closed.',
  })
  @ApiOkResponse({
    description: 'Current consent state after the accepted batch.',
  })
  @ApiBadRequestResponse({
    description: 'Invalid consent batch or idempotency key.',
  })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({
    description: 'Missing consent write scope or CSRF token.',
  })
  @ApiConflictResponse({
    description: 'Idempotency or profile availability conflict.',
  })
  @RequireScopes({
    allowedAuthorizedParties: CUSTOMER_AUTHORIZED_PARTIES,
    mode: 'all-of',
    scopes: [CUSTOMER_OPERATION_SCOPES.consentWrite],
  })
  async updateConsents(
    @Body() body: UpdateConsentsDto,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Headers('idempotency-key') idempotencyKey: string | undefined,
  ) {
    try {
      return await this.accounts.recordConsents(
        principal,
        checkedIdempotencyKey(idempotencyKey),
        body.consents,
      );
    } catch (error) {
      return mapCustomerError(error);
    }
  }

  @Post('data-requests')
  @HttpCode(HttpStatus.ACCEPTED)
  @ApiOperation({
    operationId: 'createMyDataRequest',
    summary: 'Request data export/delete',
    description:
      'Create an idempotent DSAR request for export or deletion. Execution is asynchronous.',
  })
  @ApiAcceptedResponse({
    description: 'Data request accepted.',
    type: CustomerDataRequestResponseDto,
  })
  @ApiBadRequestResponse({
    description: 'Invalid request type or idempotency key.',
  })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({
    description: 'Missing data request scope or CSRF token.',
  })
  @ApiConflictResponse({
    description: 'Idempotency or profile availability conflict.',
  })
  @RequireScopes({
    allowedAuthorizedParties: CUSTOMER_AUTHORIZED_PARTIES,
    mode: 'all-of',
    scopes: [CUSTOMER_OPERATION_SCOPES.dataRequestCreate],
  })
  async createDataRequest(
    @Body() body: CreateCustomerDataRequestDto,
    @CurrentPrincipal() principal: AccessPrincipal,
    @Headers('idempotency-key') idempotencyKey: string | undefined,
    @Req() request: RequestWithContext,
  ) {
    try {
      return await this.accounts.createDataRequest(
        principal,
        requestCorrelationId(request),
        checkedIdempotencyKey(idempotencyKey),
        body.type,
      );
    } catch (error) {
      return mapCustomerError(error);
    }
  }

  @Get('data-requests')
  @ApiOperation({
    operationId: 'listMyDataRequests',
    summary: 'List data requests',
    description:
      'Return customer-visible DSAR lifecycle state without exposing internal targets or provider errors.',
  })
  @ApiOkResponse({
    description: 'Subject-scoped data requests.',
    isArray: true,
    type: CustomerDataRequestResponseDto,
  })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({ description: 'Missing data request read scope.' })
  @RequireScopes({
    allowedAuthorizedParties: CUSTOMER_AUTHORIZED_PARTIES,
    mode: 'all-of',
    scopes: [CUSTOMER_OPERATION_SCOPES.dataRequestRead],
  })
  listDataRequests(@CurrentPrincipal() principal: AccessPrincipal) {
    return this.accounts.listDataRequests(principal);
  }

  @Get('data-requests/:requestId')
  @ApiOperation({
    operationId: 'getMyDataRequest',
    summary: 'Get data request',
    description:
      'Return one customer-visible DSAR lifecycle state for the verified subject.',
  })
  @ApiOkResponse({
    description: 'Subject-scoped data request.',
    type: CustomerDataRequestResponseDto,
  })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({ description: 'Missing data request read scope.' })
  @ApiNotFoundResponse({ description: 'Data request not found.' })
  @RequireScopes({
    allowedAuthorizedParties: CUSTOMER_AUTHORIZED_PARTIES,
    mode: 'all-of',
    scopes: [CUSTOMER_OPERATION_SCOPES.dataRequestRead],
  })
  async getDataRequest(
    @CurrentPrincipal() principal: AccessPrincipal,
    @Param('requestId', new ParseUUIDPipe({ version: '4' })) requestId: string,
  ) {
    try {
      return await this.accounts.getDataRequest(principal, requestId);
    } catch (error) {
      if (error instanceof CustomerDataRequestNotFoundError) {
        throw new NotFoundException({
          code: 'DATA_REQUEST_NOT_FOUND',
          message: 'The data request was not found.',
        });
      }
      return mapCustomerError(error);
    }
  }
}
