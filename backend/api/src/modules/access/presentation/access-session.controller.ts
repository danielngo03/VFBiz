import {
  Controller,
  Delete,
  Get,
  NotFoundException,
  Param,
  ParseUUIDPipe,
} from '@nestjs/common';
import {
  ApiForbiddenResponse,
  ApiNotFoundResponse,
  ApiOkResponse,
  ApiOperation,
  ApiParam,
  ApiTags,
  ApiUnauthorizedResponse,
} from '@nestjs/swagger';
import type { AccessPrincipal } from '../../../platform/security/access-principal';
import { RequireIdentityRealm } from '../../../platform/security/required-identity-realm';
import { RequireScopes } from '../../../platform/security/required-scopes';
import { AccessSessionService } from '../application/services/access-session.service';
import { AccessSessionNotFoundError } from '../domain/access-session';
import { CurrentAccessPrincipal } from './current-access-principal.decorator';
import {
  AccessSessionResponseDto,
  CustomerIdentitySecurityResponseDto,
  RevokeAllSessionsResponseDto,
  RevokeSessionResponseDto,
} from './access-session.dto';

const CUSTOMER_CLIENTS = ['vfbiz-customer-bff', 'vfbiz-mobile'] as const;

@Controller({ path: 'me/sessions', version: '1' })
@RequireIdentityRealm('customer')
@ApiTags('Customer')
export class AccessSessionController {
  constructor(private readonly sessions: AccessSessionService) {}

  @Get()
  @ApiOperation({
    operationId: 'listMySessions',
    summary: 'List sessions',
    description:
      'List minimized customer session projections for the verified subject.',
  })
  @ApiOkResponse({
    description: 'Customer session projections.',
    isArray: true,
    type: AccessSessionResponseDto,
  })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({ description: 'Missing session read scope.' })
  @RequireScopes({
    allowedAuthorizedParties: CUSTOMER_CLIENTS,
    mode: 'all-of',
    scopes: ['session:read'],
  })
  list(@CurrentAccessPrincipal() principal: AccessPrincipal) {
    return this.sessions.list(principal);
  }

  @Get('security')
  @ApiOperation({
    operationId: 'getMyIdentitySecurity',
    summary: 'Get identity security status',
    description:
      'Return verified email state, MFA enrollment state and MFA evidence for the current customer session.',
  })
  @ApiOkResponse({
    description: 'Current identity and session assurance status.',
    type: CustomerIdentitySecurityResponseDto,
  })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({ description: 'Missing session read scope.' })
  @RequireScopes({
    allowedAuthorizedParties: CUSTOMER_CLIENTS,
    mode: 'all-of',
    scopes: ['session:read'],
  })
  security(@CurrentAccessPrincipal() principal: AccessPrincipal) {
    return this.sessions.securityStatus(principal);
  }

  @Delete()
  @ApiOperation({
    operationId: 'revokeAllMySessions',
    summary: 'Sign out all devices',
    description:
      'Immediately deny every active local customer session and request subject-wide logout from CIAM.',
  })
  @ApiOkResponse({
    description:
      'Local denial count and identity-provider reconciliation result.',
    type: RevokeAllSessionsResponseDto,
  })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({ description: 'Missing session revoke scope.' })
  @RequireScopes({
    allowedAuthorizedParties: CUSTOMER_CLIENTS,
    mode: 'all-of',
    scopes: ['session:revoke'],
  })
  revokeAll(@CurrentAccessPrincipal() principal: AccessPrincipal) {
    return this.sessions.revokeAll(principal);
  }

  @Delete(':sessionId')
  @ApiOperation({
    operationId: 'revokeMySession',
    summary: 'Revoke session',
    description:
      'Revoke a customer session projection and deny future local API use.',
  })
  @ApiParam({ format: 'uuid', name: 'sessionId' })
  @ApiOkResponse({
    description: 'Session revoked or already revocation-intended.',
    type: RevokeSessionResponseDto,
  })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({ description: 'Missing session revoke scope.' })
  @ApiNotFoundResponse({ description: 'Session not found for this subject.' })
  @RequireScopes({
    allowedAuthorizedParties: CUSTOMER_CLIENTS,
    mode: 'all-of',
    scopes: ['session:revoke'],
  })
  async revoke(
    @CurrentAccessPrincipal() principal: AccessPrincipal,
    @Param('sessionId', new ParseUUIDPipe({ version: '4' }))
    sessionId: string,
  ) {
    try {
      return await this.sessions.revoke(principal, sessionId);
    } catch (error) {
      if (error instanceof AccessSessionNotFoundError) {
        throw new NotFoundException({
          code: 'SESSION_NOT_FOUND',
          message: 'The session was not found.',
        });
      }
      throw error;
    }
  }
}
