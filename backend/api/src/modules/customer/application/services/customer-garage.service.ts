import { Injectable } from '@nestjs/common';
import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import { CheckVehicleVariantEligibilityService } from '../../../product';
import { CustomerGarageVariantUnavailableError } from '../../domain/customer-garage';
import { CustomerGarageRepository } from '../ports/customer-garage.repository';
import { CustomerAccountService } from './customer-account.service';

@Injectable()
export class CustomerGarageService {
  constructor(
    private readonly accounts: CustomerAccountService,
    private readonly catalog: CheckVehicleVariantEligibilityService,
    private readonly repository: CustomerGarageRepository,
  ) {}

  async list(principal: AccessPrincipal) {
    await this.accounts.getProfile(principal);
    return this.repository.list(principal);
  }

  create(
    principal: AccessPrincipal,
    correlationId: string,
    idempotencyKey: string,
    input: {
      claimedVehicleVariantId: string;
      isPrimary?: boolean;
      nickname?: string | null;
    },
  ) {
    return this.createAfterValidation(
      principal,
      correlationId,
      idempotencyKey,
      input,
    );
  }

  private async createAfterValidation(
    principal: AccessPrincipal,
    correlationId: string,
    idempotencyKey: string,
    input: {
      claimedVehicleVariantId: string;
      isPrimary?: boolean;
      nickname?: string | null;
    },
  ) {
    const profile = await this.accounts.getProfile(principal);
    const command = {
      claimedVehicleVariantId: input.claimedVehicleVariantId,
      correlationId,
      idempotencyKey,
      isPrimary: input.isPrimary ?? false,
      nickname: input.nickname ?? null,
      principal,
    };
    const replay = await this.repository.findCreateReplay(command);
    if (replay !== null) return replay;

    const selectable = await this.catalog.isSelectable(
      input.claimedVehicleVariantId,
      profile.market,
    );
    if (!selectable) throw new CustomerGarageVariantUnavailableError();

    return this.repository.create(command);
  }

  update(
    principal: AccessPrincipal,
    correlationId: string,
    entryId: string,
    expectedVersion: number,
    input: { isPrimary?: boolean; nickname?: string | null },
  ) {
    return this.updateAfterProvision(
      principal,
      correlationId,
      entryId,
      expectedVersion,
      input,
    );
  }

  private async updateAfterProvision(
    principal: AccessPrincipal,
    correlationId: string,
    entryId: string,
    expectedVersion: number,
    input: { isPrimary?: boolean; nickname?: string | null },
  ) {
    await this.accounts.getProfile(principal);
    return this.repository.update({
      entryId,
      correlationId,
      expectedVersion,
      principal,
      ...input,
    });
  }

  archive(
    principal: AccessPrincipal,
    correlationId: string,
    entryId: string,
    expectedVersion: number,
  ) {
    return this.archiveAfterProvision(
      principal,
      correlationId,
      entryId,
      expectedVersion,
    );
  }

  private async archiveAfterProvision(
    principal: AccessPrincipal,
    correlationId: string,
    entryId: string,
    expectedVersion: number,
  ) {
    await this.accounts.getProfile(principal);
    return this.repository.archive(
      principal,
      correlationId,
      entryId,
      expectedVersion,
    );
  }
}
