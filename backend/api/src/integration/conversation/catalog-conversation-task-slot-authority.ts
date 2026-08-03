import { Injectable } from '@nestjs/common';
import { createHash } from 'node:crypto';
import { VehicleCatalogIdentityResolver } from '../../modules/product/vehicle-catalog-identity.resolver';
import {
  ConversationTaskSlotAuthority,
  type ConversationTaskSlotResolution,
} from '../../modules/engagement/application/ports/conversation-task-slot-authority';
import type { ConfirmedConversationContextEntity } from '../../modules/engagement/domain/runtime/conversation-runtime';

const RECEIPT_TTL_MILLISECONDS = 15 * 60 * 1_000;
const APPROVED_MARKET_CONTEXT_AUTHORITY = 'market-catalog';

/**
 * Resolves only explicitly supported slots through API-owned business
 * authorities. Unknown, ambiguous or unavailable authorities remain pending.
 */
@Injectable()
export class CatalogConversationTaskSlotAuthority extends ConversationTaskSlotAuthority {
  constructor(private readonly catalog: VehicleCatalogIdentityResolver) {
    super();
  }

  async resolve(input: {
    candidate: {
      candidateId: string;
      expectedTaskVersion: number;
      proposedValue: string;
      provenanceDigest: string;
      slot: string;
      sourceTurnId: string;
      taskId: string;
    };
    confirmedEntities: readonly ConfirmedConversationContextEntity[];
    release: {
      activationId: string;
      graphRevision: string;
      knowledgeRevision: string;
      manifestSha256: string;
      policyRevision: string;
    };
  }): Promise<ConversationTaskSlotResolution> {
    if (input.candidate.slot !== 'vehicle_model') {
      return { kind: 'unresolved', reason: 'unsupported_slot' };
    }
    const confirmedAt = new Date();
    const market = input.confirmedEntities.find(
      (entity) =>
        entity.kind === 'market' &&
        entity.authority === APPROVED_MARKET_CONTEXT_AUTHORITY &&
        entity.expiresAt.getTime() > confirmedAt.getTime(),
    );
    if (market === undefined) {
      return { kind: 'unresolved', reason: 'not_found' };
    }
    const result = await this.catalog.resolveModel({
      candidate: input.candidate.proposedValue,
      market: market.opaqueReference,
      now: confirmedAt,
    });
    if (result.kind === 'unavailable') {
      return { kind: 'failed_safely', reason: 'authority_unavailable' };
    }
    if (result.kind === 'not_found') {
      return { kind: 'unresolved', reason: 'not_found' };
    }
    const marketDigest = digest({
      authority: market.authority,
      opaqueReference: market.opaqueReference,
      provenanceDigest: market.provenanceDigest,
      sourceRevision: market.sourceRevision,
    });
    const authorityDigest = digest({
      activationId: input.release.activationId,
      marketDigest,
      modelId: result.value.modelId,
      releaseRevision: result.value.releaseRevision,
      sourceRevision: result.value.sourceRevision,
    });
    return {
      kind: 'resolved',
      receipt: {
        authority: 'vehicle_catalog',
        authorityDigest,
        confirmedAt,
        expiresAt: new Date(
          Math.min(
            market.expiresAt.getTime(),
            confirmedAt.getTime() + RECEIPT_TTL_MILLISECONDS,
          ),
        ),
        kind: 'receipt',
        opaqueReference: `vehicle:ref/v1/${digest({
          modelId: result.value.modelId,
          releaseRevision: result.value.releaseRevision,
        })}`,
        provenanceDigest: digest({
          authorityDigest,
          candidateProvenanceDigest: input.candidate.provenanceDigest,
          marketDigest,
          sourceTurnId: input.candidate.sourceTurnId,
        }),
        slot: input.candidate.slot,
        sourceRevision: result.value.sourceRevision,
        taskId: input.candidate.taskId,
      },
      slot: input.candidate.slot,
      taskId: input.candidate.taskId,
    };
  }
}

function digest(value: Readonly<Record<string, string>>): string {
  return createHash('sha256')
    .update(JSON.stringify(value), 'utf8')
    .digest('hex');
}
