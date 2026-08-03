import { ForbiddenException, Injectable } from '@nestjs/common';
import { CustomerProfileStatus } from '../../../../generated/prisma/enums';
import { Prisma } from '../../../../generated/prisma/client';
import { PrismaService } from '../../../../platform/database/prisma.service';
import { ConversationContentCipher } from '../../../../platform/security/conversation-content-cipher';
import {
  ConversationSessionRepository,
  type ConversationSubjectBudgetReservation,
  type ConversationAccessRecord,
  type ConversationMessageView,
  type ConversationSessionSummary,
  type CreateConversationSessionRecordInput,
  type CreatedConversationSessionRecord,
} from '../../application/ports/conversation-session.repository';
import type { ConversationAccessScope } from '../../domain/runtime/conversation-runtime';
import {
  conversationSubjectKeyHash,
  lockConversationSubject,
} from './conversation-persistence-lock';
import { conversationContentContext } from './conversation-content-context';

@Injectable()
export class PrismaConversationSessionRepository extends ConversationSessionRepository {
  constructor(
    private readonly prisma: PrismaService,
    private readonly contentCipher: ConversationContentCipher,
  ) {
    super();
  }

  async createSession(
    input: CreateConversationSessionRecordInput,
  ): Promise<CreatedConversationSessionRecord> {
    const created = await this.prisma.$transaction(async (transaction) => {
      const subjectKeyHash =
        input.customerSubject === null
          ? null
          : conversationSubjectKeyHash(
              input.customerSubject.issuer,
              input.customerSubject.subject,
            );
      let customerProfileId: string | null = null;
      if (input.customerSubject !== null && subjectKeyHash !== null) {
        await lockConversationSubject(transaction, subjectKeyHash);
        const profile = await transaction.customerProfile.findFirst({
          select: { id: true },
          where: {
            identitySubject: {
              issuer: input.customerSubject.issuer,
              subject: input.customerSubject.subject,
            },
            status: CustomerProfileStatus.ACTIVE,
          },
        });
        const fence =
          await transaction.conversationSubjectErasureFence.findUnique({
            select: { subjectKeyHash: true },
            where: { subjectKeyHash },
          });
        if (profile === null || fence !== null) {
          throw new ForbiddenException({
            code: 'CUSTOMER_PROFILE_UNAVAILABLE',
            message: 'The authenticated customer profile is unavailable.',
          });
        }
        customerProfileId = profile.id;
      }
      if (input.subjectBudget !== null && input.subjectBudget !== undefined) {
        await reserveSubjectBudget(transaction, input.subjectBudget);
      }
      const session = await transaction.conversationSession.create({
        data: {
          accessCapabilityHash: input.capabilityHash,
          assistantProfile: input.profile,
          customerProfileId,
          expiresAt: input.expiresAt,
          id: input.id,
          locale: input.locale,
          ownerSubjectKeyHash: subjectKeyHash,
          subjectBudgetDate: input.subjectBudget?.budgetDate ?? null,
          subjectBudgetReservedModelTokens:
            input.subjectBudget === undefined || input.subjectBudget === null
              ? null
              : BigInt(input.subjectBudget.reserveModelTokens),
          subjectBudgetReservedCostMicros:
            input.subjectBudget === undefined || input.subjectBudget === null
              ? null
              : BigInt(input.subjectBudget.reserveCostMicros),
          subjectBudgetReconciledAt: null,
          assistantReleaseActivationId: input.release.activationId,
          assistantReleaseEffectiveAt: input.release.effectiveAt,
          assistantReleaseEnvelopeSha256:
            input.release.activationEnvelopeSha256,
          assistantReleaseExpiresAt: input.release.expiresAt,
          assistantReleaseGraphRevision: input.release.graphRevision,
          assistantReleaseKnowledgeRevision: input.release.knowledgeRevision,
          assistantReleaseManifestSha256: input.release.manifestSha256,
          assistantReleasePointerRevision: BigInt(
            input.release.pointerRevision,
          ),
          policyRevision: input.release.policyRevision,
          retentionUntil: input.retentionUntil,
          status: 'active',
        },
        select: {
          assistantProfile: true,
          createdAt: true,
          id: true,
          locale: true,
        },
      });
      await transaction.conversationRuntime.create({
        data: {
          conversationSessionId: session.id,
          remainingCostMicros: BigInt(input.initialCostBudgetMicros),
          remainingModelTokens: BigInt(input.initialModelTokenBudget),
        },
      });
      return session;
    });
    return {
      createdAt: created.createdAt,
      expiresAt: input.expiresAt,
      id: created.id,
      locale: created.locale as 'vi' | 'en',
      profile: created.assistantProfile as
        'public_customer' | 'authenticated_customer',
      retentionUntil: input.retentionUntil,
    };
  }

  async findAccessRecord(
    sessionId: string,
  ): Promise<ConversationAccessRecord | null> {
    const record = await this.prisma.conversationSession.findUnique({
      select: {
        accessCapabilityHash: true,
        customerProfile: {
          select: {
            identitySubject: { select: { issuer: true, subject: true } },
          },
        },
        expiresAt: true,
        id: true,
        status: true,
      },
      where: { id: sessionId },
    });
    if (record === null) return null;
    return {
      capabilityHash: record.accessCapabilityHash,
      customerSubject: record.customerProfile?.identitySubject ?? null,
      expiresAt: record.expiresAt,
      id: record.id,
      status: record.status,
    };
  }

  async findSessionSummary(
    sessionId: string,
  ): Promise<ConversationSessionSummary | null> {
    const record = await this.prisma.conversationSession.findUnique({
      select: {
        assistantProfile: true,
        createdAt: true,
        expiresAt: true,
        id: true,
        locale: true,
        retentionUntil: true,
      },
      where: { id: sessionId },
    });
    if (record === null) return null;
    return {
      createdAt: record.createdAt,
      expiresAt: record.expiresAt,
      id: record.id,
      locale: record.locale as 'vi' | 'en',
      profile: record.assistantProfile as
        'public_customer' | 'authenticated_customer',
      retentionUntil: record.retentionUntil,
    };
  }

  async listMessages(
    sessionId: string,
    accessScope: ConversationAccessScope,
  ): Promise<readonly ConversationMessageView[]> {
    const access = await this.findAccessRecord(sessionId);
    if (!messageScopeMatches(access, accessScope)) return [];
    const messages = await this.prisma.conversationMessage.findMany({
      orderBy: { sequence: 'asc' },
      select: {
        citations: {
          orderBy: { id: 'asc' },
          select: {
            retrievedAt: true,
            sourceId: true,
            sourceRevision: true,
            title: true,
            uri: true,
          },
        },
        createdAt: true,
        id: true,
        outcome: true,
        contentEnvelope: true,
        redactedContent: true,
        role: true,
        sequence: true,
      },
      where: { conversationSessionId: sessionId },
    });
    return messages.map((message) => ({
      citations: message.citations.map((citation) => ({
        retrievedAt: citation.retrievedAt,
        revision: citation.sourceRevision,
        sourceId: citation.sourceId,
        title: citation.title,
        uri: citation.uri,
      })),
      content:
        message.contentEnvelope === null
          ? (message.redactedContent ?? '')
          : this.contentCipher.decrypt(
              message.contentEnvelope,
              conversationContentContext(
                accessScope,
                sessionId,
                message.id,
                'message',
              ),
            ),
      createdAt: message.createdAt,
      id: message.id,
      outcome: message.outcome,
      role: message.role,
      sequence: Number(message.sequence),
    }));
  }
}

async function reserveSubjectBudget(
  transaction: Prisma.TransactionClient,
  reservation: ConversationSubjectBudgetReservation,
): Promise<void> {
  const existing = await transaction.conversationSubjectBudget.findUnique({
    where: {
      subjectKeyHash_budgetDate: {
        subjectKeyHash: reservation.subjectKeyHash,
        budgetDate: reservation.budgetDate,
      },
    },
  });
  if (existing === null) {
    if (
      reservation.reserveModelTokens > reservation.dailyModelTokenLimit ||
      reservation.reserveCostMicros > reservation.dailyCostLimitMicros
    ) {
      throw new Error('CUSTOMER_CHAT_DAILY_BUDGET_EXHAUSTED');
    }
    await transaction.conversationSubjectBudget.create({
      data: {
        subjectKeyHash: reservation.subjectKeyHash,
        budgetDate: reservation.budgetDate,
        remainingModelTokens: BigInt(
          reservation.dailyModelTokenLimit - reservation.reserveModelTokens,
        ),
        remainingCostMicros: BigInt(
          reservation.dailyCostLimitMicros - reservation.reserveCostMicros,
        ),
      },
    });
    return;
  }
  if (
    existing.remainingModelTokens < BigInt(reservation.reserveModelTokens) ||
    existing.remainingCostMicros < BigInt(reservation.reserveCostMicros)
  ) {
    throw new Error('CUSTOMER_CHAT_DAILY_BUDGET_EXHAUSTED');
  }
  await transaction.conversationSubjectBudget.update({
    where: {
      subjectKeyHash_budgetDate: {
        subjectKeyHash: reservation.subjectKeyHash,
        budgetDate: reservation.budgetDate,
      },
    },
    data: {
      remainingModelTokens: {
        decrement: BigInt(reservation.reserveModelTokens),
      },
      remainingCostMicros: {
        decrement: BigInt(reservation.reserveCostMicros),
      },
      version: { increment: BigInt(1) },
    },
  });
}

function messageScopeMatches(
  access: ConversationAccessRecord | null,
  scope: ConversationAccessScope,
): boolean {
  if (access === null || access.status !== 'active') return false;
  if (scope.kind === 'public_capability') {
    return (
      access.customerSubject === null &&
      access.capabilityHash === scope.capabilityHash
    );
  }
  return (
    access.customerSubject?.issuer === scope.issuer &&
    access.customerSubject.subject === scope.subject
  );
}
