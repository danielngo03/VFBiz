import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { EnvironmentVariables } from '../../../../platform/config/env.schema';
import { PrismaService } from '../../../../platform/database/prisma.service';
import {
  ActiveAssistantReleaseProjection,
  type AssistantReleaseBinding,
} from '../../application/ports/active-assistant-release-projection';

@Injectable()
export class PrismaActiveAssistantReleaseProjection extends ActiveAssistantReleaseProjection {
  private readonly environment: EnvironmentVariables['NODE_ENV'];

  constructor(
    private readonly prisma: PrismaService,
    config: ConfigService<EnvironmentVariables, true>,
  ) {
    super();
    this.environment = config.get('NODE_ENV', { infer: true });
  }

  async resolve(input: {
    now: Date;
    profile: 'authenticated_customer' | 'public_customer';
  }): Promise<AssistantReleaseBinding | null> {
    const record =
      await this.prisma.activeAssistantReleaseProjection.findUnique({
        where: {
          assistantProfile_environment: {
            assistantProfile: input.profile,
            environment: this.environment,
          },
        },
      });
    if (
      record === null ||
      record.status !== 'active' ||
      record.effectiveAt > input.now ||
      record.expiresAt <= input.now
    ) {
      return null;
    }
    return {
      activationEnvelopeSha256: record.activationEnvelopeSha256,
      activationId: record.activationId,
      effectiveAt: record.effectiveAt,
      expiresAt: record.expiresAt,
      graphRevision: record.graphRevision,
      knowledgeRevision: record.knowledgeRevision,
      manifestSha256: record.manifestSha256,
      pointerRevision: Number(record.pointerRevision),
      policyRevision: record.policyRevision,
    };
  }
}
