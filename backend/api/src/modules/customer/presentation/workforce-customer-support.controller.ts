import {
  BadRequestException,
  Controller,
  Get,
  Headers,
  Query,
  Req,
} from '@nestjs/common';
import { ApiExcludeController } from '@nestjs/swagger';
import type { AccessPrincipal } from '../../../platform/security/access-principal';
import { CurrentPrincipal } from '../../../platform/security/current-principal.decorator';
import { RequireAnyAuthenticationMethod } from '../../../platform/security/required-authentication-methods';
import { RequireCapabilities } from '../../../platform/security/required-capabilities';
import { RequireIdentityRealm } from '../../../platform/security/required-identity-realm';
import {
  requestCorrelationId,
  type RequestWithContext,
} from '../../../platform/http/request-context';
import { WorkforceCustomerSupportService } from '../application/services/workforce-customer-support.service';
import {
  WorkforceCustomerAccessReasonError,
  WorkforceCustomerSearchValidationError,
} from '../domain/workforce-customer-support';

@Controller({ path: 'workforce/customer-support/customers', version: '1' })
@ApiExcludeController()
@RequireIdentityRealm('workforce')
@RequireAnyAuthenticationMethod(['otp', 'webauthn'])
@RequireCapabilities({
  capabilities: ['customer-support.customer.read'],
  mode: 'all-of',
})
export class WorkforceCustomerSupportController {
  constructor(private readonly customers: WorkforceCustomerSupportService) {}

  @Get()
  async search(
    @CurrentPrincipal() principal: AccessPrincipal,
    @Query('query') query = '',
    @Query('limit') rawLimit = '20',
    @Headers('x-access-reason') reason = '',
    @Req() request: RequestWithContext,
  ) {
    const limit = Number(rawLimit);
    if (!Number.isInteger(limit) || limit < 1 || limit > 50) {
      throw new BadRequestException({
        code: 'CUSTOMER_SEARCH_LIMIT_INVALID',
        message: 'limit must be an integer from 1 to 50.',
      });
    }
    try {
      return await this.customers.search({
        correlationId: requestCorrelationId(request),
        limit,
        principal,
        query,
        reason,
      });
    } catch (error) {
      if (error instanceof WorkforceCustomerSearchValidationError) {
        throw new BadRequestException({
          code: 'CUSTOMER_SEARCH_QUERY_INVALID',
          message: error.message,
        });
      }
      if (error instanceof WorkforceCustomerAccessReasonError) {
        throw new BadRequestException({
          code: 'CUSTOMER_ACCESS_REASON_REQUIRED',
          message: error.message,
        });
      }
      throw error;
    }
  }
}
