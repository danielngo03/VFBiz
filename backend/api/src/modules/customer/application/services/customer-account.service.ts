import { Injectable } from '@nestjs/common';
import { createHash, randomUUID } from 'node:crypto';
import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import { CustomerAccountRepository } from '../ports/customer-account.repository';
import type {
  CommunicationPreferences,
  ConsentPurpose,
  ConsentState,
  CustomerDataRequestType,
  CustomerLocale,
  CustomerMarket,
  CustomerRequestSource,
} from '../../domain/customer-account';
import { CustomerConsentBatchValidationError } from '../../domain/customer-account';

export interface CustomerProfilePatch {
  readonly displayName?: string | null;
  readonly locale?: CustomerLocale;
  readonly market?: CustomerMarket;
  readonly communicationPreferences?: Partial<CommunicationPreferences>;
  readonly timezone?: string;
}

export interface ConsentCommand {
  readonly policyVersion: string;
  readonly purpose: ConsentPurpose;
  readonly state: ConsentState;
}

function sourceFor(principal: AccessPrincipal): CustomerRequestSource {
  return principal.authorizedParty === 'vfbiz-mobile'
    ? 'mobile'
    : 'customer_portal';
}

function consentCorrelationId(
  requestCorrelationId: string,
  purpose: ConsentPurpose,
): string {
  const value = createHash('sha256')
    .update(`${requestCorrelationId}:${purpose}`, 'utf8')
    .digest('hex');
  return [
    value.slice(0, 8),
    value.slice(8, 12),
    `4${value.slice(13, 16)}`,
    `a${value.slice(17, 20)}`,
    value.slice(20, 32),
  ].join('-');
}

@Injectable()
export class CustomerAccountService {
  constructor(private readonly repository: CustomerAccountRepository) {}

  getProfile(principal: AccessPrincipal) {
    return this.repository.provisionProfile(principal);
  }

  updateProfile(
    principal: AccessPrincipal,
    correlationId: string,
    expectedVersion: number,
    patch: CustomerProfilePatch,
  ) {
    return this.repository.updateProfile({
      ...patch,
      correlationId,
      expectedVersion,
      principal,
    });
  }

  listConsents(principal: AccessPrincipal) {
    return this.repository.listCurrentConsents(principal);
  }

  recordConsents(
    principal: AccessPrincipal,
    idempotencyKey: string,
    commands: readonly ConsentCommand[],
  ) {
    const purposes = new Set<ConsentPurpose>();
    for (const command of commands) {
      if (purposes.has(command.purpose)) {
        throw new CustomerConsentBatchValidationError();
      }
      purposes.add(command.purpose);
    }
    const source = sourceFor(principal);
    return this.repository.recordConsents(
      commands.map((command) => ({
        ...command,
        correlationId: consentCorrelationId(idempotencyKey, command.purpose),
        idempotencyKey,
        principal,
        source,
      })),
    );
  }

  createDataRequest(
    principal: AccessPrincipal,
    correlationId: string,
    idempotencyKey: string,
    type: CustomerDataRequestType,
  ) {
    return this.repository.createDataRequest({
      correlationId: correlationId || randomUUID(),
      idempotencyKey,
      principal,
      source: sourceFor(principal),
      type,
    });
  }

  listDataRequests(principal: AccessPrincipal) {
    return this.repository.listDataRequests(principal);
  }

  getDataRequest(principal: AccessPrincipal, requestId: string) {
    return this.repository.getDataRequest(principal, requestId);
  }
}
