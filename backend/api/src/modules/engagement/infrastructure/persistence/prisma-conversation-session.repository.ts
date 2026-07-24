import { ForbiddenException, Injectable } from '@nestjs/common';
import { CustomerProfileStatus } from '../../../../generated/prisma/enums';
import { PrismaService } from '../../../../platform/database/prisma.service';
import {
  ConversationSessionRepository,
  type ConversationAccessRecord,
  type ConversationMessageView,
  type CreateConversationSessionRecordInput,
  type CreatedConversationSessionRecord,
} from '../../application/ports/conversation-session.repository';

@Injectable()
export class PrismaConversationSessionRepository extends ConversationSessionRepository {
  constructor(private readonly prisma: PrismaService) {
    super();
  }

  async createSession(
    input: CreateConversationSessionRecordInput,
  ): Promise<CreatedConversationSessionRecord> {
    let customerProfileId: string | null = null;
    if (input.customerSubject !== null) {
      const profile = await this.prisma.customerProfile.findFirst({
        select: { id: true },
        where: {
          identitySubject: {
            issuer: input.customerSubject.issuer,
            subject: input.customerSubject.subject,
          },
          status: CustomerProfileStatus.ACTIVE,
        },
      });
      if (profile === null) {
        throw new ForbiddenException({
          code: 'CUSTOMER_PROFILE_UNAVAILABLE',
          message: 'The authenticated customer profile is unavailable.',
        });
      }
      customerProfileId = profile.id;
    }

    const created = await this.prisma.conversationSession.create({
      data: {
        accessCapabilityHash: input.capabilityHash,
        assistantProfile: input.profile,
        customerProfileId,
        expiresAt: input.expiresAt,
        id: input.id,
        locale: input.locale,
        policyRevision: input.policyRevision,
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
    return {
      createdAt: created.createdAt,
      id: created.id,
      locale: created.locale as 'vi' | 'en',
      profile: created.assistantProfile as
        'public_customer' | 'authenticated_customer',
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

  async listMessages(
    sessionId: string,
  ): Promise<readonly ConversationMessageView[]> {
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
        redactedContent: true,
        role: true,
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
      content: message.redactedContent ?? '',
      createdAt: message.createdAt,
      id: message.id,
      outcome: message.outcome,
      role: message.role,
    }));
  }
}
