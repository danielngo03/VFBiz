import { Injectable } from '@nestjs/common';
import { createHash } from 'node:crypto';
import {
  ConversationTaskSlotAuthority,
  type ConversationTaskProposal,
} from '../ports/conversation-task-slot-authority';
import type { ConversationAccessScope } from '../../domain/runtime/conversation-runtime';
import type { ConfirmedConversationContextEntity } from '../../domain/runtime/conversation-runtime';
import {
  assertConversationTaskDelta,
  type ConversationTaskContext,
  type ConversationTaskDelta,
  type ConversationTaskSlotReference,
} from '../../domain/runtime/conversation-task-context';
import { ConversationRuntimeClock } from './conversation-runtime.repository';

export class ConversationTaskSlotResolutionError extends Error {
  constructor(
    readonly code:
      | 'AUTHORITY_FAILED'
      | 'CANDIDATE_BINDING_MISMATCH'
      | 'RECEIPT_BINDING_MISMATCH',
  ) {
    super(code);
    this.name = ConversationTaskSlotResolutionError.name;
  }
}

@Injectable()
export class ResolveConversationTaskSlotsService {
  constructor(
    private readonly authority: ConversationTaskSlotAuthority,
    private readonly clock: ConversationRuntimeClock,
  ) {}

  async resolve(input: {
    accessScope: ConversationAccessScope;
    assistantProfile: 'authenticated_customer' | 'public_customer';
    currentTask: ConversationTaskContext | null;
    confirmedEntities: readonly ConfirmedConversationContextEntity[];
    proposal: ConversationTaskProposal;
    signal?: AbortSignal;
  }): Promise<ConversationTaskDelta> {
    const { proposal } = input;
    const current = input.currentTask;
    const now = this.clock.now();
    if (
      proposal.sourceTurnId.length === 0 ||
      proposal.expiresAt <= now ||
      (current !== null &&
        (proposal.taskId !== current.taskId ||
          proposal.expectedTaskVersion !== current.taskVersion ||
          proposal.authorizationContextDigest !==
            current.authorizationContextDigest))
    ) {
      throw new ConversationTaskSlotResolutionError(
        'CANDIDATE_BINDING_MISMATCH',
      );
    }

    const candidatesBySlot = new Map(
      proposal.slotCandidates.map((candidate) => [candidate.slot, candidate]),
    );
    if (
      candidatesBySlot.size !== proposal.slotCandidates.length ||
      proposal.slotCandidates.some(
        (candidate) =>
          candidate.taskId !== proposal.taskId ||
          candidate.expectedTaskVersion !== proposal.expectedTaskVersion ||
          candidate.sourceTurnId !== proposal.sourceTurnId ||
          !proposal.pendingSlots.includes(candidate.slot),
      )
    ) {
      throw new ConversationTaskSlotResolutionError(
        'CANDIDATE_BINDING_MISMATCH',
      );
    }

    const receipts: Record<string, ConversationTaskSlotReference> = {
      ...(current?.collectedSlots ?? {}),
    };
    const confirmedSlots: string[] = [];
    for (const candidate of proposal.slotCandidates) {
      const resolution = await this.authority.resolve({
        accessScope: input.accessScope,
        assistantProfile: input.assistantProfile,
        candidate,
        confirmedEntities: input.confirmedEntities,
        intent: proposal.intent,
        release: proposal.release,
        signal: input.signal,
      });
      if (
        resolution.kind === 'rejected' ||
        resolution.kind === 'failed_safely'
      ) {
        throw new ConversationTaskSlotResolutionError('AUTHORITY_FAILED');
      }
      if (resolution.kind === 'unresolved') continue;
      const receipt = resolution.receipt;
      const verificationTime = this.clock.now();
      if (
        resolution.taskId !== proposal.taskId ||
        resolution.slot !== candidate.slot ||
        receipt.taskId !== proposal.taskId ||
        receipt.slot !== candidate.slot ||
        receipt.confirmedAt > verificationTime ||
        receipt.expiresAt <= verificationTime ||
        receipt.expiresAt <= receipt.confirmedAt ||
        receipt.expiresAt > proposal.expiresAt
      ) {
        throw new ConversationTaskSlotResolutionError(
          'RECEIPT_BINDING_MISMATCH',
        );
      }
      receipts[candidate.slot] = receipt;
      confirmedSlots.push(candidate.slot);
    }

    const pendingSlots = proposal.pendingSlots.filter(
      (slot) => !confirmedSlots.includes(slot),
    );
    const material = {
      authorizationContextDigest: proposal.authorizationContextDigest,
      candidateProvenance: proposal.slotCandidates.map(
        ({ candidateId, provenanceDigest, slot }) => ({
          candidateId,
          provenanceDigest,
          slot,
        }),
      ),
      collectedSlots: serializeReceipts(receipts),
      expectedTaskVersion: proposal.expectedTaskVersion,
      expiresAt: proposal.expiresAt.toISOString(),
      intent: proposal.intent,
      intentRevision: proposal.intentRevision,
      nextState: pendingSlots.length > 0 ? 'awaiting_clarification' : 'active',
      operation: 'upsert',
      pendingSlots,
      proposalProvenanceDigest: proposal.provenanceDigest,
      release: proposal.release,
      sourceTurnId: proposal.sourceTurnId,
      taskId: proposal.taskId,
    } as const;
    const delta: ConversationTaskDelta = {
      ...material,
      collectedSlots: receipts,
      expiresAt: proposal.expiresAt,
      provenanceDigest: createHash('sha256')
        .update(JSON.stringify(material), 'utf8')
        .digest('hex'),
    };
    assertConversationTaskDelta(delta);
    return delta;
  }
}

function serializeReceipts(
  receipts: Readonly<Record<string, ConversationTaskSlotReference>>,
) {
  return Object.fromEntries(
    Object.entries(receipts).map(([slot, receipt]) => [
      slot,
      {
        ...receipt,
        confirmedAt: receipt.confirmedAt.toISOString(),
        expiresAt: receipt.expiresAt.toISOString(),
      },
    ]),
  );
}
