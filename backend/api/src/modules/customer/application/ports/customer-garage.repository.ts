import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import type { CustomerGarageEntryView } from '../../domain/customer-garage';

export interface CreateGarageEntryInput {
  readonly claimedVehicleVariantId: string;
  readonly correlationId: string;
  readonly idempotencyKey: string;
  readonly isPrimary: boolean;
  readonly nickname: string | null;
  readonly principal: AccessPrincipal;
}

export interface UpdateGarageEntryInput {
  readonly correlationId: string;
  readonly entryId: string;
  readonly expectedVersion: number;
  readonly isPrimary?: boolean;
  readonly nickname?: string | null;
  readonly principal: AccessPrincipal;
}

export abstract class CustomerGarageRepository {
  abstract list(
    principal: AccessPrincipal,
  ): Promise<readonly CustomerGarageEntryView[]>;

  abstract create(
    input: CreateGarageEntryInput,
  ): Promise<CustomerGarageEntryView>;

  abstract findCreateReplay(
    input: CreateGarageEntryInput,
  ): Promise<CustomerGarageEntryView | null>;

  abstract update(
    input: UpdateGarageEntryInput,
  ): Promise<CustomerGarageEntryView>;

  abstract archive(
    principal: AccessPrincipal,
    correlationId: string,
    entryId: string,
    expectedVersion: number,
  ): Promise<CustomerGarageEntryView>;
}
