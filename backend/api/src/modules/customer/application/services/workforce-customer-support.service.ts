import { Injectable } from '@nestjs/common';
import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import { WorkforceEntitlementReader } from '../../../../platform/security/workforce-entitlement-reader';
import { WorkforceCustomerSupportRepository } from '../ports/workforce-customer-support.repository';
import {
  WorkforceCustomerAccessReasonError,
  WorkforceCustomerSearchValidationError,
} from '../../domain/workforce-customer-support';

const CAPABILITY = 'customer-support.customer.read';

@Injectable()
export class WorkforceCustomerSupportService {
  constructor(
    private readonly authorization: WorkforceEntitlementReader,
    private readonly repository: WorkforceCustomerSupportRepository,
  ) {}

  async search(input: {
    readonly correlationId: string;
    readonly limit: number;
    readonly principal: AccessPrincipal;
    readonly query: string;
    readonly reason: string;
  }) {
    const query = input.query.trim();
    if (query.length < 3) throw new WorkforceCustomerSearchValidationError();
    const reason = input.reason.trim();
    if (reason.length < 10) throw new WorkforceCustomerAccessReasonError();
    const entitlements = await this.authorization.getEntitlements(
      input.principal,
    );
    const grant = entitlements?.capabilities.find(
      (capability) => capability.key === CAPABILITY,
    );
    const global = grant?.scopes.some((scope) => scope.type === 'global');
    const allowedMarkets = global
      ? null
      : (grant?.scopes
          .filter((scope) => scope.type === 'market')
          .map((scope) => scope.ref) ?? []);
    return this.repository.search({
      actorRef: `${input.principal.issuer}|${input.principal.subject}`,
      allowedMarkets,
      correlationId: input.correlationId,
      limit: Math.min(Math.max(input.limit, 1), 50),
      query,
      reason,
    });
  }
}
