import { createHash } from 'node:crypto';
import { Injectable } from '@nestjs/common';
import { Prisma } from '../../../../generated/prisma/client';
import { PrismaService } from '../../../../platform/database/prisma.service';
import {
  ConversationContentCipher,
  type ConversationContentEnvelopeV1,
} from '../../../../platform/security/conversation-content-cipher';
import {
  MAX_CITATION_IDENTIFIER_CHARACTERS,
  MAX_CITATION_TITLE_CHARACTERS,
  MAX_CITATION_URI_CHARACTERS,
  MAX_CONVERSATION_CITATIONS,
  MAX_CONVERSATION_OUTPUT_CHARACTERS,
  MAX_PUBLIC_EVENT_PAYLOAD_BYTES,
  copyConversationPublicEvent,
  encodePublicEventCursor,
  sameConversationAccessScope,
  type ConversationAccessScope,
  type ConversationCitation,
  type ConversationPublicEvent,
  type ConversationRuntimeSnapshot,
  type ConversationTurn,
} from '../../domain/runtime/conversation-runtime';
import {
  ConversationRuntimeRepository,
  type AcceptedMessageReplay,
  type ConversationRuntimeCommit,
  type ConversationRuntimeCommitResult,
  type ConversationCancellationDispatch,
  type ConversationDispatchCandidate,
  type ConversationPublicEventReadResult,
  type ConversationTurnExecutionContext,
} from '../../application/runtime/conversation-runtime.repository';
import {
  conversationSubjectKeyHash,
  lockConversationSession,
  lockConversationSubject,
} from './conversation-persistence-lock';
import { conversationContentContext } from './conversation-content-context';

type Transaction = Prisma.TransactionClient;
type SessionAccessRow = {
  accessCapabilityHash: string | null;
  assistantProfile: string;
  expiresAt: Date;
  retentionUntil: Date;
  status: string;
  customerProfile: {
    identitySubject: { issuer: string; subject: string };
  } | null;
};

const SERIALIZABLE_RETRY_LIMIT = 3;
const ACTIVE_HANDOFF_STATUSES = ['requested', 'queued', 'connected'] as const;

export class ConversationRuntimePersistenceCorruptionError extends Error {
  constructor() {
    super('Conversation runtime persistence is invalid');
    this.name = 'ConversationRuntimePersistenceCorruptionError';
  }
}

@Injectable()
export class PrismaConversationRuntimeRepository extends ConversationRuntimeRepository {
  constructor(
    private readonly prisma: PrismaService,
    private readonly contentCipher: ConversationContentCipher,
  ) {
    super();
  }

  async commit(
    transition: ConversationRuntimeCommit,
  ): Promise<ConversationRuntimeCommitResult> {
    for (let attempt = 1; attempt <= SERIALIZABLE_RETRY_LIMIT; attempt += 1) {
      try {
        return await this.prisma.$transaction(
          (transaction) => this.commitTransaction(transaction, transition),
          { isolationLevel: Prisma.TransactionIsolationLevel.Serializable },
        );
      } catch (error) {
        if (
          error instanceof Prisma.PrismaClientKnownRequestError &&
          (error.code === 'P2034' || error.code === 'P2002') &&
          attempt < SERIALIZABLE_RETRY_LIMIT
        ) {
          continue;
        }
        throw error;
      }
    }
    throw new ConversationRuntimePersistenceCorruptionError();
  }

  async findAcceptedMessage(
    sessionId: string,
    accessScope: ConversationAccessScope,
    clientMessageId: string,
    now: Date,
  ): Promise<AcceptedMessageReplay | null> {
    const session = await this.findSessionAccess(this.prisma, sessionId);
    if (
      session === null ||
      !matchesAccessScope(session, accessScope) ||
      !runtimeReadable(session, now)
    ) {
      return null;
    }
    const turn = await this.prisma.conversationTurn.findUnique({
      where: {
        conversationSessionId_clientMessageId: {
          clientMessageId,
          conversationSessionId: sessionId,
        },
      },
    });
    if (turn === null) return null;
    const requestFingerprint = this.contentCipher.decrypt(
      turn.requestFingerprintEnvelope,
      conversationContentContext(
        accessScope,
        sessionId,
        turn.id,
        'request-fingerprint',
      ),
    );
    return {
      accessScope: copyAccessScope(accessScope),
      requestFingerprint,
      result: {
        clientMessageId: turn.clientMessageId,
        conversationVersion: safeNumber(turn.acceptedVersion),
        eventCursor: encodePublicEventCursor(
          safeNumber(turn.acceptedEventSequence),
        ),
        receivedSequence: safeNumber(turn.receivedSequence),
        turnId: turn.id,
      },
    };
  }

  async findDispatchCandidates(
    now: Date,
    limit: number,
  ): Promise<readonly ConversationDispatchCandidate[]> {
    const rows = await this.prisma.conversationTurn.findMany({
      include: {
        conversationSession: {
          include: {
            customerProfile: {
              select: {
                identitySubject: { select: { issuer: true, subject: true } },
              },
            },
            runtime: true,
          },
        },
      },
      orderBy: [{ createdAt: 'asc' }, { receivedSequence: 'asc' }],
      take: limit,
      where: {
        conversationSession: {
          expiresAt: { gt: now },
          retentionUntil: { gt: now },
          status: 'active',
        },
        OR: [
          { dispatchAvailableAt: { lte: now }, status: 'accepted' },
          { leaseExpiresAt: { lte: now }, status: 'claimed' },
        ],
      },
    });
    return rows.flatMap((row): readonly ConversationDispatchCandidate[] => {
      const runtime = row.conversationSession.runtime;
      const accessScope = accessScopeFromSession(row.conversationSession);
      if (runtime === null || accessScope === null) return [];
      return [
        {
          accessScope: copyAccessScope(accessScope),
          attempts: row.dispatchAttempts,
          expectedVersion: safeNumber(runtime.version),
          nextFencingToken: safeNumber(runtime.fencingTokenHighWatermark) + 1,
          sessionId: row.conversationSessionId,
          turnId: row.id,
        },
      ];
    });
  }

  async claimCancellationDispatches(
    now: Date,
    leaseUntil: Date,
    limit: number,
  ): Promise<readonly ConversationCancellationDispatch[]> {
    return this.prisma.$transaction(async (transaction) => {
      const rows = await transaction.outboxEvent.findMany({
        orderBy: { createdAt: 'asc' },
        take: limit,
        where: {
          availableAt: { lte: now },
          eventType: 'conversation.ai.cancel.requested',
          status: { in: ['pending', 'processing'] },
        },
      });
      const claimed: ConversationCancellationDispatch[] = [];
      for (const row of rows) {
        const locked = await transaction.outboxEvent.updateMany({
          data: {
            attempts: { increment: 1 },
            availableAt: leaseUntil,
            status: 'processing',
          },
          where: {
            availableAt: { lte: now },
            id: row.id,
            status: { in: ['pending', 'processing'] },
          },
        });
        if (locked.count !== 1) continue;
        const payload = parseCancellationDispatchPayload(row.payload);
        if (payload === null) {
          await transaction.outboxEvent.update({
            data: { status: 'failed' },
            where: { id: row.id },
          });
          continue;
        }
        const session = await transaction.conversationSession.findUnique({
          include: {
            customerProfile: {
              select: {
                identitySubject: { select: { issuer: true, subject: true } },
              },
            },
            runtimeTurns: {
              select: {
                maxCostMicros: true,
                maxModelTokens: true,
              },
              where: { id: payload.turnId },
            },
          },
          where: { id: payload.sessionId },
        });
        const accessScope =
          session === null ? null : accessScopeFromSession(session);
        const turn = session?.runtimeTurns[0];
        if (
          session === null ||
          accessScope === null ||
          turn === undefined ||
          session.assistantReleaseActivationId === null ||
          session.assistantReleaseEffectiveAt === null ||
          session.assistantReleaseEnvelopeSha256 === null ||
          session.assistantReleaseExpiresAt === null ||
          session.assistantReleaseGraphRevision === null ||
          session.assistantReleaseKnowledgeRevision === null ||
          session.assistantReleaseManifestSha256 === null ||
          session.assistantReleasePointerRevision === null
        ) {
          await transaction.outboxEvent.update({
            data: { status: 'failed' },
            where: { id: row.id },
          });
          continue;
        }
        claimed.push({
          accessScope: copyAccessScope(accessScope),
          assistantProfile: session.assistantProfile as
            'authenticated_customer' | 'public_customer',
          attempts: row.attempts + 1,
          budget: {
            maxCostMicros: safeNumber(turn.maxCostMicros),
            maxModelTokens: safeNumber(turn.maxModelTokens),
          },
          conversationVersion: payload.conversationVersion,
          correlationId: row.correlationId,
          dispatchId: row.id,
          fencingToken: payload.fencingToken,
          locale: session.locale as 'en' | 'vi',
          release: {
            activationEnvelopeSha256: session.assistantReleaseEnvelopeSha256,
            activationId: session.assistantReleaseActivationId,
            effectiveAt: session.assistantReleaseEffectiveAt,
            expiresAt: session.assistantReleaseExpiresAt,
            graphRevision: session.assistantReleaseGraphRevision,
            knowledgeRevision: session.assistantReleaseKnowledgeRevision,
            manifestSha256: session.assistantReleaseManifestSha256,
            pointerRevision: safeNumber(
              session.assistantReleasePointerRevision,
            ),
            policyRevision: session.policyRevision,
          },
          policyRevision: session.policyRevision,
          reason: payload.reason,
          requestId: row.id,
          sessionId: payload.sessionId,
          turnId: payload.turnId,
        });
      }
      return claimed;
    });
  }

  async completeCancellationDispatch(dispatchId: string): Promise<void> {
    await this.prisma.outboxEvent.updateMany({
      data: { publishedAt: new Date(), status: 'completed' },
      where: { id: dispatchId, status: 'processing' },
    });
  }

  async retryCancellationDispatch(
    dispatchId: string,
    availableAt: Date,
    terminal: boolean,
  ): Promise<void> {
    await this.prisma.outboxEvent.updateMany({
      data: {
        availableAt,
        status: terminal ? 'failed' : 'pending',
      },
      where: { id: dispatchId, status: 'processing' },
    });
  }

  async recordTurnDispatchFailure(input: {
    correlationId: string;
    failureCode: string;
    fencingToken: number;
    nextAttemptAt: Date;
    sessionId: string;
    terminal: boolean;
    turnId: string;
  }): Promise<boolean> {
    return this.prisma.$transaction(async (transaction) => {
      const updated = await transaction.conversationTurn.updateMany({
        data: {
          dispatchAttempts: { increment: 1 },
          dispatchAvailableAt: input.nextAttemptAt,
          dispatchFailedAt: input.terminal ? new Date() : null,
          dispatchFailureCode: input.failureCode,
          leaseExpiresAt: input.terminal ? undefined : null,
          status: input.terminal ? 'claimed' : 'accepted',
          workerId: input.terminal ? undefined : null,
        },
        where: {
          conversationSessionId: input.sessionId,
          fencingToken: BigInt(input.fencingToken),
          id: input.turnId,
          status: 'claimed',
        },
      });
      if (updated.count !== 1) return false;
      if (input.terminal) {
        await transaction.auditEvent.create({
          data: {
            action: 'conversation.turn.dispatch.dead-lettered',
            actorRef: null,
            actorType: 'system',
            correlationId: input.correlationId,
            metadata: {
              failureCode: input.failureCode,
              fencingToken: input.fencingToken,
            },
            outcome: 'failed',
            resourceId: input.turnId,
            resourceType: 'conversation_turn',
          },
        });
      }
      return true;
    });
  }

  async getSnapshot(
    sessionId: string,
    accessScope: ConversationAccessScope,
    now: Date,
  ): Promise<ConversationRuntimeSnapshot | null> {
    const session = await this.prisma.conversationSession.findUnique({
      include: {
        customerProfile: {
          select: {
            identitySubject: { select: { issuer: true, subject: true } },
          },
        },
        runtime: true,
        runtimeTurns: {
          include: {
            customerMessage: {
              select: { contentEnvelope: true },
            },
          },
          orderBy: { receivedSequence: 'asc' },
        },
      },
      where: { id: sessionId },
    });
    if (
      session === null ||
      session.runtime === null ||
      !matchesAccessScope(session, accessScope) ||
      !runtimeReadable(session, now)
    ) {
      return null;
    }

    const turns = session.runtimeTurns.map((turn): ConversationTurn => {
      const envelope = turn.customerMessage
        .contentEnvelope as unknown as ConversationContentEnvelopeV1 | null;
      if (envelope === null) {
        throw new ConversationRuntimePersistenceCorruptionError();
      }
      const receiptParts = [
        turn.assistantReleaseCandidateSha256,
        turn.assistantReleaseEnvelopeSha256,
        turn.assistantReleasePointerRevision,
        turn.assistantReleaseReceiptIssuedAt,
        turn.assistantReleaseReceiptExpiresAt,
        turn.assistantReleaseRequestId,
        turn.assistantReleaseConversationVersion,
        turn.assistantReleaseFencingToken,
        turn.assistantReleaseLeaseId,
      ];
      const populatedReceiptParts = receiptParts.filter(
        (part) => part !== null,
      ).length;
      if (
        populatedReceiptParts !== 0 &&
        (populatedReceiptParts !== receiptParts.length ||
          turn.assistantReleaseRevision === null)
      ) {
        throw new ConversationRuntimePersistenceCorruptionError();
      }
      return {
        assistantReleaseRevision: turn.assistantReleaseRevision,
        assistantReleaseReceipt:
          populatedReceiptParts === 0
            ? null
            : {
                activationEnvelopeSha256: turn.assistantReleaseEnvelopeSha256!,
                activationId: turn.assistantReleaseRevision!,
                candidateSha256: turn.assistantReleaseCandidateSha256!,
                conversationVersion: safeNumber(
                  turn.assistantReleaseConversationVersion!,
                ),
                expiresAt: storedDate(turn.assistantReleaseReceiptExpiresAt!),
                fencingToken: safeNumber(turn.assistantReleaseFencingToken!),
                issuedAt: storedDate(turn.assistantReleaseReceiptIssuedAt!),
                leaseId: turn.assistantReleaseLeaseId!,
                pointerRevision: safeNumber(
                  turn.assistantReleasePointerRevision!,
                ),
                requestId: turn.assistantReleaseRequestId!,
                sessionId,
                turnId: turn.id,
              },
        budget: {
          maxCostMicros: safeNumber(turn.maxCostMicros),
          maxModelTokens: safeNumber(turn.maxModelTokens),
        },
        cancellationAuthority:
          turn.cancellationAuthority as ConversationTurn['cancellationAuthority'],
        cancellationReason:
          turn.cancellationReason as ConversationTurn['cancellationReason'],
        cancelledAt:
          turn.cancelledAt === null ? null : storedDate(turn.cancelledAt),
        claim:
          turn.status !== 'claimed' ||
          turn.workerId === null ||
          turn.fencingToken === null ||
          turn.leaseExpiresAt === null
            ? null
            : {
                fencingToken: safeNumber(turn.fencingToken),
                leaseExpiresAt: storedDate(turn.leaseExpiresAt),
                workerId: turn.workerId,
              },
        clientMessageId: turn.clientMessageId,
        content: this.contentCipher.decrypt(
          envelope,
          conversationContentContext(
            accessScope,
            sessionId,
            turn.customerMessageId,
            'message',
          ),
        ),
        id: turn.id,
        receivedSequence: safeNumber(turn.receivedSequence),
        requestFingerprint: this.contentCipher.decrypt(
          turn.requestFingerprintEnvelope,
          conversationContentContext(
            accessScope,
            sessionId,
            turn.id,
            'request-fingerprint',
          ),
        ),
        status: turn.status as ConversationTurn['status'],
        usage:
          turn.usedCostMicros === null || turn.usedModelTokens === null
            ? null
            : {
                costMicros: safeNumber(turn.usedCostMicros),
                modelTokens: safeNumber(turn.usedModelTokens),
              },
      };
    });

    return {
      accessScope: copyAccessScope(accessScope),
      budget: {
        remainingCostMicros: safeNumber(session.runtime.remainingCostMicros),
        remainingModelTokens: safeNumber(session.runtime.remainingModelTokens),
      },
      fencingTokenHighWatermark: safeNumber(
        session.runtime.fencingTokenHighWatermark,
      ),
      id: sessionId,
      lastPublicEventSequence: safeNumber(
        session.runtime.lastPublicEventSequence,
      ),
      lastReceivedSequence: safeNumber(session.runtime.lastReceivedSequence),
      status: session.runtime.runtimeStatus as 'handoff' | 'open',
      turns,
      version: safeNumber(session.runtime.version),
    };
  }

  async getTurnExecutionContext(
    sessionId: string,
    accessScope: ConversationAccessScope,
    turnId: string,
    now: Date,
  ): Promise<ConversationTurnExecutionContext | null> {
    const session = await this.prisma.conversationSession.findUnique({
      include: {
        customerProfile: {
          select: {
            identitySubject: { select: { issuer: true, subject: true } },
          },
        },
        runtime: { select: { version: true } },
        runtimeTurns: {
          include: {
            customerMessage: { select: { contentEnvelope: true } },
          },
          where: { id: turnId },
        },
      },
      where: { id: sessionId },
    });
    if (
      session === null ||
      session.runtime === null ||
      !matchesAccessScope(session, accessScope) ||
      !runtimeReadable(session, now)
    ) {
      return null;
    }
    const turn = session.runtimeTurns[0];
    if (
      turn === undefined ||
      turn.status !== 'claimed' ||
      turn.fencingToken === null ||
      turn.customerMessage.contentEnvelope === null ||
      session.assistantReleaseActivationId === null ||
      session.assistantReleaseEffectiveAt === null ||
      session.assistantReleaseEnvelopeSha256 === null ||
      session.assistantReleaseExpiresAt === null ||
      session.assistantReleaseGraphRevision === null ||
      session.assistantReleaseKnowledgeRevision === null ||
      session.assistantReleaseManifestSha256 === null ||
      session.assistantReleasePointerRevision === null
    ) {
      return null;
    }
    const envelope = turn.customerMessage
      .contentEnvelope as unknown as ConversationContentEnvelopeV1;
    return {
      accessScope: copyAccessScope(accessScope),
      assistantProfile: session.assistantProfile as
        'authenticated_customer' | 'public_customer',
      budget: {
        maxCostMicros: safeNumber(turn.maxCostMicros),
        maxModelTokens: safeNumber(turn.maxModelTokens),
      },
      content: this.contentCipher.decrypt(
        envelope,
        conversationContentContext(
          accessScope,
          sessionId,
          turn.customerMessageId,
          'message',
        ),
      ),
      conversationVersion: safeNumber(session.runtime.version),
      fencingToken: safeNumber(turn.fencingToken),
      locale: session.locale as 'en' | 'vi',
      release: {
        activationEnvelopeSha256: session.assistantReleaseEnvelopeSha256,
        activationId: session.assistantReleaseActivationId,
        effectiveAt: session.assistantReleaseEffectiveAt,
        expiresAt: session.assistantReleaseExpiresAt,
        graphRevision: session.assistantReleaseGraphRevision,
        knowledgeRevision: session.assistantReleaseKnowledgeRevision,
        manifestSha256: session.assistantReleaseManifestSha256,
        pointerRevision: safeNumber(session.assistantReleasePointerRevision),
        policyRevision: session.policyRevision,
      },
      policyRevision: session.policyRevision,
      sessionId,
      turnId,
    };
  }

  async listPublicEvents(
    sessionId: string,
    accessScope: ConversationAccessScope,
    afterSequence: number | null,
    limit: number,
    now: Date,
  ): Promise<ConversationPublicEventReadResult> {
    const session = await this.findSessionAccess(this.prisma, sessionId);
    if (session === null || !matchesAccessScope(session, accessScope)) {
      return { outcome: 'not-found' };
    }
    const retentionUntil = storedDate(session.retentionUntil);
    if (retentionUntil.getTime() <= now.getTime()) {
      return {
        earliestAvailableCursor: null,
        latestAvailableCursor: null,
        outcome: 'resync-required',
        reason: 'retention_expired',
        retentionUntil,
      };
    }
    const window = await this.prisma.conversationPublicEvent.aggregate({
      _max: { sequence: true },
      _min: { sequence: true },
      where: { conversationSessionId: sessionId },
    });
    const oldestSequence =
      window._min.sequence === null ? null : safeNumber(window._min.sequence);
    const latestSequence =
      window._max.sequence === null ? null : safeNumber(window._max.sequence);
    if (
      afterSequence !== null &&
      ((oldestSequence !== null && afterSequence < oldestSequence - 1) ||
        (latestSequence === null && afterSequence > 0))
    ) {
      return {
        earliestAvailableCursor:
          oldestSequence === null
            ? null
            : encodePublicEventCursor(oldestSequence),
        latestAvailableCursor:
          latestSequence === null
            ? null
            : encodePublicEventCursor(latestSequence),
        outcome: 'resync-required',
        reason: 'cursor_expired',
        retentionUntil,
      };
    }
    if (
      afterSequence !== null &&
      latestSequence !== null &&
      afterSequence > latestSequence
    ) {
      return {
        earliestAvailableCursor: encodePublicEventCursor(oldestSequence!),
        latestAvailableCursor: encodePublicEventCursor(latestSequence),
        outcome: 'resync-required',
        reason: 'cursor_out_of_range',
        retentionUntil,
      };
    }
    const rows = await this.prisma.conversationPublicEvent.findMany({
      orderBy: { sequence: 'asc' },
      take: limit,
      where: {
        conversationSessionId: sessionId,
        sequence: { gt: BigInt(afterSequence ?? 0) },
      },
    });
    const events = rows.map((row) => {
      const sequence = safeNumber(row.sequence);
      const payload = parsePayload(
        this.contentCipher.decrypt(
          row.payloadEnvelope,
          conversationContentContext(
            accessScope,
            sessionId,
            row.id,
            'public-event-payload',
          ),
        ),
        row.type,
        row.schemaVersion,
      );
      const payloadTurnId = 'turnId' in payload ? payload.turnId : null;
      if (payloadTurnId !== row.conversationTurnId) {
        throw new ConversationRuntimePersistenceCorruptionError();
      }
      return copyConversationPublicEvent({
        cursor: encodePublicEventCursor(sequence),
        eventId: row.id,
        occurredAt: storedDate(row.occurredAt),
        payload,
        schemaVersion: row.schemaVersion,
        sequence,
        sessionId,
        type: row.type,
      } as ConversationPublicEvent);
    });
    return { events, outcome: 'events' };
  }

  async purgeExpiredSessions(now: Date, limit: number): Promise<number> {
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 1_000) {
      throw new ConversationRuntimePersistenceCorruptionError();
    }
    return this.prisma.$transaction(
      async (transaction) => {
        const candidates = await transaction.$queryRaw<
          { id: string }[]
        >(Prisma.sql`
          SELECT session."id"
          FROM "conversation_session" session
          WHERE session."retentionUntil" <= ${now}
            AND EXISTS (
              SELECT 1 FROM "conversation_runtime" runtime
              WHERE runtime."conversationSessionId" = session."id"
            )
          ORDER BY session."retentionUntil" ASC, session."id" ASC
          LIMIT ${limit}
        `);
        const candidateIds = candidates.map(({ id }) => id).sort();
        if (candidateIds.length === 0) return 0;
        for (const sessionId of candidateIds) {
          await lockConversationSession(transaction, sessionId);
        }
        await transaction.$queryRaw<{ id: string }[]>(Prisma.sql`
          SELECT "id"
          FROM "conversation_session"
          WHERE "id" IN (${Prisma.join(candidateIds)})
          ORDER BY "id" ASC
          FOR UPDATE
        `);
        const eligible = await transaction.conversationSession.findMany({
          orderBy: [{ retentionUntil: 'asc' }, { id: 'asc' }],
          select: { id: true },
          where: {
            id: { in: candidateIds },
            retentionUntil: { lte: now },
            runtime: { isNot: null },
            runtimeTurns: {
              none: { leaseExpiresAt: { gt: now }, status: 'claimed' },
            },
            supportHandoffs: {
              none: { status: { in: [...ACTIVE_HANDOFF_STATUSES] } },
            },
          },
        });
        return purgeSessionsTransaction(
          transaction,
          eligible.map(({ id }) => id),
        );
      },
      { isolationLevel: Prisma.TransactionIsolationLevel.Serializable },
    );
  }

  async purgeCustomerSubject(
    deletionRequestId: string,
    issuer: string,
    subject: string,
  ): Promise<number> {
    const subjectKeyHash = conversationSubjectKeyHash(issuer, subject);
    return this.prisma.$transaction(
      async (transaction) => {
        await lockConversationSubject(transaction, subjectKeyHash);
        await transaction.conversationSubjectErasureFence.upsert({
          create: { deletionRequestId, subjectKeyHash },
          update: {},
          where: { subjectKeyHash },
        });
        const sessions = await transaction.conversationSession.findMany({
          orderBy: { id: 'asc' },
          select: { id: true },
          where: { ownerSubjectKeyHash: subjectKeyHash },
        });
        const sessionIds = sessions.map(({ id }) => id);
        for (const sessionId of sessionIds) {
          await lockConversationSession(transaction, sessionId);
        }
        return purgeSessionsTransaction(transaction, sessionIds);
      },
      { isolationLevel: Prisma.TransactionIsolationLevel.Serializable },
    );
  }

  private async commitTransaction(
    transaction: Transaction,
    transition: ConversationRuntimeCommit,
  ): Promise<ConversationRuntimeCommitResult> {
    await lockConversationSession(transaction, transition.sessionId);
    const session = await transaction.conversationSession.findUnique({
      include: {
        customerProfile: {
          select: {
            identitySubject: { select: { issuer: true, subject: true } },
          },
        },
        runtime: true,
      },
      where: { id: transition.sessionId },
    });
    if (
      session === null ||
      session.runtime === null ||
      !runtimeReadable(session, transition.now)
    ) {
      return { actualVersion: 0, outcome: 'version-conflict' };
    }
    if (!matchesAccessScope(session, transition.accessScope)) {
      return {
        actualVersion: safeNumber(session.runtime.version),
        outcome: 'version-conflict',
      };
    }

    const replay = transition.acceptedMessageReplay;
    if (replay !== undefined) {
      const existing = await transaction.conversationTurn.findUnique({
        where: {
          conversationSessionId_clientMessageId: {
            clientMessageId: replay.result.clientMessageId,
            conversationSessionId: transition.sessionId,
          },
        },
      });
      if (existing !== null) {
        const requestFingerprint = this.contentCipher.decrypt(
          existing.requestFingerprintEnvelope,
          conversationContentContext(
            transition.accessScope,
            transition.sessionId,
            existing.id,
            'request-fingerprint',
          ),
        );
        return {
          outcome: 'message-replay',
          replay: replayFromTurn(
            existing,
            transition.accessScope,
            requestFingerprint,
          ),
        };
      }
    }

    const updated = await transaction.conversationRuntime.updateMany({
      data: {
        fencingTokenHighWatermark: BigInt(
          transition.nextState.fencingTokenHighWatermark,
        ),
        lastPublicEventSequence: BigInt(
          transition.nextState.lastPublicEventSequence,
        ),
        lastReceivedSequence: BigInt(transition.nextState.lastReceivedSequence),
        remainingCostMicros: BigInt(
          transition.nextState.budget.remainingCostMicros,
        ),
        remainingModelTokens: BigInt(
          transition.nextState.budget.remainingModelTokens,
        ),
        runtimeStatus: transition.nextState.status,
        version: BigInt(transition.nextState.version),
      },
      where: {
        conversationSessionId: transition.sessionId,
        version: BigInt(transition.expectedVersion),
      },
    });
    if (updated.count !== 1) {
      const actual = await transaction.conversationRuntime.findUniqueOrThrow({
        select: { version: true },
        where: { conversationSessionId: transition.sessionId },
      });
      return {
        actualVersion: safeNumber(actual.version),
        outcome: 'version-conflict',
      };
    }

    const event = transition.events[0];
    if (event === undefined || transition.events.length !== 1) {
      throw new ConversationRuntimePersistenceCorruptionError();
    }

    const isSessionScopedEvent =
      event.type === 'session.closed' ||
      (event.type === 'handoff.requested' &&
        event.payload.turnId === undefined);
    if (isSessionScopedEvent) {
      // A session-level event, not a turn one: no ConversationTurn row to
      // create or update. session.closed never has one; handoff.requested
      // only has one when it came from completeTurn's handoff branch, not
      // from an explicit customer-initiated request.
    } else {
      const turn = transition.nextState.turns.find(
        (candidate) => candidate.id === event.payload.turnId,
      );
      if (turn === undefined) {
        throw new ConversationRuntimePersistenceCorruptionError();
      }

      if (event.type === 'message.accepted') {
        await this.createAcceptedTurn(
          transaction,
          transition.accessScope,
          event,
          turn,
          transition.nextState.version,
        );
      } else {
        if (turn.assistantReleaseReceipt !== null) {
          const [databaseClock] = await transaction.$queryRaw<
            readonly [{ now: Date }]
          >(Prisma.sql`SELECT clock_timestamp() AS "now"`);
          if (
            databaseClock === undefined ||
            turn.assistantReleaseReceipt.expiresAt.getTime() <=
              databaseClock.now.getTime()
          ) {
            throw new ConversationRuntimePersistenceCorruptionError();
          }
        }
        const cancellationFence =
          event.type === 'turn.cancelled'
            ? await transaction.conversationTurn.findUnique({
                select: {
                  fencingToken: true,
                  status: true,
                },
                where: { id: turn.id },
              })
            : null;
        await this.updateTurn(transaction, transition.sessionId, turn);
        if (
          event.type === 'turn.cancelled' &&
          cancellationFence?.status === 'claimed' &&
          cancellationFence.fencingToken !== null
        ) {
          await transaction.outboxEvent.create({
            data: {
              aggregateId: transition.sessionId,
              aggregateType: 'conversation',
              correlationId: event.eventId,
              eventType: 'conversation.ai.cancel.requested',
              eventVersion: 1,
              payload: {
                conversationVersion: transition.expectedVersion,
                fencingToken: cancellationFence.fencingToken.toString(),
                reason: event.payload.reason,
                sessionId: transition.sessionId,
                turnId: event.payload.turnId,
              },
            },
          });
        }
      }
    }
    await this.persistEvent(
      transaction,
      transition.accessScope,
      session.retentionUntil,
      event,
    );
    await this.persistCompletionProjection(
      transaction,
      transition.accessScope,
      event,
    );
    return { outcome: 'committed' };
  }

  private async createAcceptedTurn(
    transaction: Transaction,
    accessScope: ConversationAccessScope,
    event: Extract<ConversationPublicEvent, { type: 'message.accepted' }>,
    turn: ConversationTurn,
    acceptedVersion: number,
  ): Promise<void> {
    const envelope = this.contentCipher.encrypt(
      turn.content,
      conversationContentContext(
        accessScope,
        event.sessionId,
        turn.id,
        'message',
      ),
    );
    const fingerprintEnvelope = this.contentCipher.encrypt(
      turn.requestFingerprint,
      conversationContentContext(
        accessScope,
        event.sessionId,
        turn.id,
        'request-fingerprint',
      ),
    );
    await transaction.conversationMessage.create({
      data: {
        contentEnvelope: json(envelope),
        contentKeyId: envelope.keyId,
        conversationSessionId: event.sessionId,
        id: turn.id,
        role: 'customer',
        sequence: BigInt(event.sequence),
      },
    });
    await transaction.conversationTurn.create({
      data: {
        acceptedEventSequence: BigInt(event.sequence),
        acceptedVersion: BigInt(acceptedVersion),
        clientMessageId: turn.clientMessageId,
        conversationSessionId: event.sessionId,
        customerMessageId: turn.id,
        id: turn.id,
        maxCostMicros: BigInt(turn.budget.maxCostMicros),
        maxModelTokens: BigInt(turn.budget.maxModelTokens),
        receivedSequence: BigInt(turn.receivedSequence),
        requestFingerprintEnvelope: json(fingerprintEnvelope),
        requestFingerprintKeyId: fingerprintEnvelope.keyId,
        status: turn.status,
      },
    });
  }

  private async updateTurn(
    transaction: Transaction,
    sessionId: string,
    turn: ConversationTurn,
  ): Promise<void> {
    const result = await transaction.conversationTurn.updateMany({
      data: {
        cancellationAuthority: turn.cancellationAuthority,
        cancellationReason: turn.cancellationReason,
        cancelledAt: turn.cancelledAt,
        fencingToken:
          turn.claim?.fencingToken === undefined
            ? null
            : BigInt(turn.claim.fencingToken),
        leaseExpiresAt: turn.claim?.leaseExpiresAt ?? null,
        workerId: turn.claim?.workerId ?? null,
        status: turn.status,
        assistantReleaseRevision: turn.assistantReleaseRevision,
        assistantReleaseCandidateSha256:
          turn.assistantReleaseReceipt?.candidateSha256 ?? null,
        assistantReleaseEnvelopeSha256:
          turn.assistantReleaseReceipt?.activationEnvelopeSha256 ?? null,
        assistantReleasePointerRevision:
          turn.assistantReleaseReceipt === null
            ? null
            : BigInt(turn.assistantReleaseReceipt.pointerRevision),
        assistantReleaseReceiptIssuedAt:
          turn.assistantReleaseReceipt?.issuedAt ?? null,
        assistantReleaseReceiptExpiresAt:
          turn.assistantReleaseReceipt?.expiresAt ?? null,
        assistantReleaseRequestId:
          turn.assistantReleaseReceipt?.requestId ?? null,
        assistantReleaseConversationVersion:
          turn.assistantReleaseReceipt === null
            ? null
            : BigInt(turn.assistantReleaseReceipt.conversationVersion),
        assistantReleaseFencingToken:
          turn.assistantReleaseReceipt === null
            ? null
            : BigInt(turn.assistantReleaseReceipt.fencingToken),
        assistantReleaseLeaseId: turn.assistantReleaseReceipt?.leaseId ?? null,
        usedCostMicros:
          turn.usage === null ? null : BigInt(turn.usage.costMicros),
        usedModelTokens:
          turn.usage === null ? null : BigInt(turn.usage.modelTokens),
      },
      where: { conversationSessionId: sessionId, id: turn.id },
    });
    if (result.count !== 1) {
      throw new ConversationRuntimePersistenceCorruptionError();
    }
  }

  private async persistEvent(
    transaction: Transaction,
    accessScope: ConversationAccessScope,
    retentionUntil: Date,
    event: ConversationPublicEvent,
  ): Promise<void> {
    const envelope = this.contentCipher.encrypt(
      JSON.stringify(event.payload),
      conversationContentContext(
        accessScope,
        event.sessionId,
        event.eventId,
        'public-event-payload',
      ),
    );
    await transaction.conversationPublicEvent.create({
      data: {
        conversationSessionId: event.sessionId,
        conversationTurnId:
          event.type === 'session.closed'
            ? null
            : (event.payload.turnId ?? null),
        id: event.eventId,
        occurredAt: event.occurredAt,
        payloadEnvelope: json(envelope),
        payloadKeyId: envelope.keyId,
        retentionUntil,
        schemaVersion: event.schemaVersion,
        sequence: BigInt(event.sequence),
        type: event.type,
      },
    });
  }

  private async persistCompletionProjection(
    transaction: Transaction,
    accessScope: ConversationAccessScope,
    event: ConversationPublicEvent,
  ): Promise<void> {
    if (event.type !== 'turn.completed' && event.type !== 'handoff.requested') {
      return;
    }
    const messageId = event.eventId;
    const message =
      event.type === 'handoff.requested'
        ? event.payload.customerMessage
        : event.payload.message;
    const envelope = this.contentCipher.encrypt(
      message,
      conversationContentContext(
        accessScope,
        event.sessionId,
        messageId,
        'message',
      ),
    );
    await transaction.conversationMessage.create({
      data: {
        citations:
          event.type === 'turn.completed' &&
          event.payload.outcome === 'answered'
            ? {
                create: event.payload.citations.map((citation) => ({
                  evidenceHash: citationHash(citation),
                  retrievedAt: citation.retrievedAt,
                  sourceId: citation.sourceId,
                  sourceRevision: citation.revision,
                  title: citation.title,
                  uri: citation.uri,
                })),
              }
            : undefined,
        contentEnvelope: json(envelope),
        contentKeyId: envelope.keyId,
        conversationSessionId: event.sessionId,
        id: messageId,
        outcome:
          event.type === 'handoff.requested'
            ? 'handed_off'
            : event.payload.outcome,
        role: 'assistant',
        sequence: BigInt(event.sequence),
      },
    });
    if (event.type === 'handoff.requested') {
      await transaction.supportHandoff.create({
        data: {
          conversationSessionId: event.sessionId,
          id: event.payload.handoffId,
          reasonCode: event.payload.reason,
          status: 'queued',
        },
      });
    }
  }

  private async findSessionAccess(
    transaction: Transaction | PrismaService,
    sessionId: string,
  ): Promise<SessionAccessRow | null> {
    return transaction.conversationSession.findUnique({
      select: {
        accessCapabilityHash: true,
        assistantProfile: true,
        customerProfile: {
          select: {
            identitySubject: { select: { issuer: true, subject: true } },
          },
        },
        expiresAt: true,
        retentionUntil: true,
        status: true,
      },
      where: { id: sessionId },
    });
  }
}

function matchesAccessScope(
  session: SessionAccessRow | null,
  accessScope: ConversationAccessScope,
): boolean {
  if (session === null) return false;
  const stored = accessScopeFromSession(session);
  return stored !== null && sameConversationAccessScope(stored, accessScope);
}

function accessScopeFromSession(
  session: SessionAccessRow,
): ConversationAccessScope | null {
  if (
    session.assistantProfile === 'public_customer' &&
    session.accessCapabilityHash !== null
  ) {
    return {
      capabilityHash: session.accessCapabilityHash,
      kind: 'public_capability',
      profile: 'public_customer',
    };
  }
  if (
    session.assistantProfile === 'authenticated_customer' &&
    session.customerProfile !== null
  ) {
    return {
      issuer: session.customerProfile.identitySubject.issuer,
      kind: 'authenticated_customer',
      profile: 'authenticated_customer',
      subject: session.customerProfile.identitySubject.subject,
    };
  }
  return null;
}

function parseCancellationDispatchPayload(value: Prisma.JsonValue): {
  readonly conversationVersion: number;
  readonly fencingToken: number;
  readonly reason:
    'budget_exhausted' | 'system_shutdown' | 'timeout' | 'user_interrupt';
  readonly sessionId: string;
  readonly turnId: string;
} | null {
  if (isRecord(value)) {
    try {
      exactKeys(value, [
        'conversationVersion',
        'fencingToken',
        'reason',
        'sessionId',
        'turnId',
      ]);
    } catch {
      return null;
    }
  }
  if (
    !isRecord(value) ||
    !isIdentifier(value.sessionId) ||
    !isIdentifier(value.turnId) ||
    typeof value.fencingToken !== 'string' ||
    !/^[1-9]\d*$/.test(value.fencingToken) ||
    !Number.isSafeInteger(value.conversationVersion) ||
    Number(value.conversationVersion) < 1 ||
    typeof value.reason !== 'string' ||
    ![
      'budget_exhausted',
      'system_shutdown',
      'timeout',
      'user_interrupt',
    ].includes(value.reason)
  ) {
    return null;
  }
  const fencingToken = Number(value.fencingToken);
  if (!Number.isSafeInteger(fencingToken)) return null;
  return {
    conversationVersion: Number(value.conversationVersion),
    fencingToken,
    reason: value.reason as
      'budget_exhausted' | 'system_shutdown' | 'timeout' | 'user_interrupt',
    sessionId: value.sessionId,
    turnId: value.turnId,
  };
}

function runtimeReadable(
  session: Pick<SessionAccessRow, 'expiresAt' | 'retentionUntil' | 'status'>,
  now: Date,
): boolean {
  return (
    session.status === 'active' &&
    storedDate(session.expiresAt).getTime() > now.getTime() &&
    storedDate(session.retentionUntil).getTime() > now.getTime()
  );
}

async function purgeSessionsTransaction(
  transaction: Transaction,
  sessionIds: readonly string[],
): Promise<number> {
  if (sessionIds.length === 0) return 0;
  await transaction.supportHandoff.deleteMany({
    where: { conversationSessionId: { in: [...sessionIds] } },
  });
  const deleted = await transaction.conversationSession.deleteMany({
    where: { id: { in: [...sessionIds] } },
  });
  return deleted.count;
}

function replayFromTurn(
  turn: {
    acceptedEventSequence: bigint;
    acceptedVersion: bigint;
    clientMessageId: string;
    id: string;
    receivedSequence: bigint;
  },
  accessScope: ConversationAccessScope,
  requestFingerprint: string,
): AcceptedMessageReplay {
  return {
    accessScope: copyAccessScope(accessScope),
    requestFingerprint,
    result: {
      clientMessageId: turn.clientMessageId,
      conversationVersion: safeNumber(turn.acceptedVersion),
      eventCursor: encodePublicEventCursor(
        safeNumber(turn.acceptedEventSequence),
      ),
      receivedSequence: safeNumber(turn.receivedSequence),
      turnId: turn.id,
    },
  };
}

function parsePayload(
  serialized: string,
  type: string,
  schemaVersion: number,
): ConversationPublicEvent['payload'] {
  if (Buffer.byteLength(serialized, 'utf8') > MAX_PUBLIC_EVENT_PAYLOAD_BYTES) {
    throw new ConversationRuntimePersistenceCorruptionError();
  }
  if (schemaVersion !== 1) {
    throw new ConversationRuntimePersistenceCorruptionError();
  }
  let payload: unknown;
  try {
    payload = JSON.parse(serialized);
  } catch {
    throw new ConversationRuntimePersistenceCorruptionError();
  }
  if (!isRecord(payload)) {
    throw new ConversationRuntimePersistenceCorruptionError();
  }
  if (type === 'session.closed') {
    exactKeys(payload, []);
    return payload as unknown as ConversationPublicEvent['payload'];
  }
  if (type === 'handoff.requested') {
    // Unlike every other turn-scoped event, turnId is optional here: an
    // explicit customer-initiated handoff has no owning turn, while one
    // raised from completeTurn's handoff branch always has one.
    const hasTurnId = 'turnId' in payload;
    exactKeys(
      payload,
      hasTurnId
        ? ['customerMessage', 'handoffId', 'reason', 'status', 'turnId']
        : ['customerMessage', 'handoffId', 'reason', 'status'],
    );
    if (
      (hasTurnId && !isIdentifier(payload.turnId)) ||
      !isBoundedString(
        payload.customerMessage,
        1,
        MAX_CONVERSATION_OUTPUT_CHARACTERS,
      ) ||
      !isIdentifier(payload.handoffId) ||
      payload.status !== 'queued' ||
      ![
        'customer_requested',
        'insufficient_evidence',
        'policy_required',
        'safety_risk',
        'tool_unavailable',
      ].includes(String(payload.reason))
    ) {
      throw new ConversationRuntimePersistenceCorruptionError();
    }
    return payload as unknown as ConversationPublicEvent['payload'];
  }
  if (!isIdentifier(payload.turnId)) {
    throw new ConversationRuntimePersistenceCorruptionError();
  }
  if (type === 'message.accepted') {
    exactKeys(payload, ['clientMessageId', 'receivedSequence', 'turnId']);
    if (
      !isIdentifier(payload.clientMessageId) ||
      !isPositiveSafeInteger(payload.receivedSequence)
    ) {
      throw new ConversationRuntimePersistenceCorruptionError();
    }
    return payload as unknown as ConversationPublicEvent['payload'];
  }
  if (type === 'turn.processing') {
    exactKeys(payload, ['turnId']);
    return payload as unknown as ConversationPublicEvent['payload'];
  }
  if (type === 'turn.cancelled') {
    exactKeys(payload, ['reason', 'turnId']);
    if (
      ![
        'budget_exhausted',
        'system_shutdown',
        'timeout',
        'user_interrupt',
      ].includes(String(payload.reason))
    ) {
      throw new ConversationRuntimePersistenceCorruptionError();
    }
    return payload as unknown as ConversationPublicEvent['payload'];
  }
  if (type === 'turn.completed') {
    if (payload.outcome === 'refused') {
      exactKeys(payload, ['message', 'outcome', 'turnId']);
      if (
        !isBoundedString(payload.message, 1, MAX_CONVERSATION_OUTPUT_CHARACTERS)
      ) {
        throw new ConversationRuntimePersistenceCorruptionError();
      }
      return payload as unknown as ConversationPublicEvent['payload'];
    }
    if (payload.outcome !== 'answered' || !Array.isArray(payload.citations)) {
      throw new ConversationRuntimePersistenceCorruptionError();
    }
    exactKeys(payload, ['citations', 'message', 'outcome', 'turnId']);
    if (
      !isBoundedString(
        payload.message,
        1,
        MAX_CONVERSATION_OUTPUT_CHARACTERS,
      ) ||
      payload.citations.length > MAX_CONVERSATION_CITATIONS
    ) {
      throw new ConversationRuntimePersistenceCorruptionError();
    }
    payload.citations = payload.citations.map(parseCitation);
    return payload as unknown as ConversationPublicEvent['payload'];
  }
  throw new ConversationRuntimePersistenceCorruptionError();
}

function parseCitation(candidate: unknown): ConversationCitation {
  if (!isRecord(candidate)) {
    throw new ConversationRuntimePersistenceCorruptionError();
  }
  exactKeys(candidate, ['retrievedAt', 'revision', 'sourceId', 'title', 'uri']);
  if (
    typeof candidate.retrievedAt !== 'string' ||
    !isBoundedString(
      candidate.revision,
      1,
      MAX_CITATION_IDENTIFIER_CHARACTERS,
    ) ||
    !isBoundedString(
      candidate.sourceId,
      1,
      MAX_CITATION_IDENTIFIER_CHARACTERS,
    ) ||
    !isBoundedString(candidate.title, 1, MAX_CITATION_TITLE_CHARACTERS) ||
    !isBoundedString(candidate.uri, 1, MAX_CITATION_URI_CHARACTERS)
  ) {
    throw new ConversationRuntimePersistenceCorruptionError();
  }
  const retrievedAt = new Date(candidate.retrievedAt);
  if (!Number.isFinite(retrievedAt.getTime())) {
    throw new ConversationRuntimePersistenceCorruptionError();
  }
  return {
    retrievedAt,
    revision: candidate.revision,
    sourceId: candidate.sourceId,
    title: candidate.title,
    uri: candidate.uri,
  };
}

function exactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): void {
  const actual = Object.keys(value).sort();
  const canonical = [...expected].sort();
  if (
    actual.length !== canonical.length ||
    actual.some((key, index) => key !== canonical[index])
  ) {
    throw new ConversationRuntimePersistenceCorruptionError();
  }
}

function isIdentifier(value: unknown): value is string {
  return isBoundedString(value, 1, 160);
}

function isBoundedString(
  value: unknown,
  minimum: number,
  maximum: number,
): value is string {
  return (
    typeof value === 'string' &&
    value.length >= minimum &&
    value.length <= maximum
  );
}

function isPositiveSafeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && Number(value) > 0;
}

function safeNumber(value: bigint): number {
  const converted = Number(value);
  if (!Number.isSafeInteger(converted) || converted < 0) {
    throw new ConversationRuntimePersistenceCorruptionError();
  }
  return converted;
}

function storedDate(value: unknown): Date {
  const candidate =
    value instanceof Date
      ? new Date(value.getTime())
      : typeof value === 'string'
        ? new Date(value)
        : null;
  if (candidate === null || !Number.isFinite(candidate.getTime())) {
    throw new ConversationRuntimePersistenceCorruptionError();
  }
  return candidate;
}

function json(value: ConversationContentEnvelopeV1): Prisma.InputJsonValue {
  return value as unknown as Prisma.InputJsonValue;
}

function citationHash(citation: ConversationCitation): string {
  return createHash('sha256')
    .update(
      JSON.stringify({
        retrievedAt: citation.retrievedAt.toISOString(),
        revision: citation.revision,
        sourceId: citation.sourceId,
        title: citation.title,
        uri: citation.uri,
      }),
      'utf8',
    )
    .digest('hex');
}

function copyAccessScope(
  accessScope: ConversationAccessScope,
): ConversationAccessScope {
  return { ...accessScope };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
