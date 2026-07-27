import { Module } from '@nestjs/common';
import { DatabaseModule } from '../../platform/database/database.module';
import { ConversationContentProtectionModule } from '../../platform/security/conversation-content-protection.module';
import { InternalAiTrustModule } from '../../platform/security/internal-ai-trust.module';
import { RedisModule } from '../../platform/redis/redis.module';
import { ConversationEventReplayBuffer } from './application/ports/conversation-event-replay-buffer';
import { ConversationEventStreamRegistry } from './application/ports/conversation-event-stream-registry';
import { ActiveAssistantReleaseProjection } from './application/ports/active-assistant-release-projection';
import { ConversationSessionRepository } from './application/ports/conversation-session.repository';
import { ConversationAiTransport } from './application/runtime/conversation-ai.transport';
import {
  ConversationRuntimeClock,
  ConversationRuntimeIdGenerator,
  ConversationRuntimeRepository,
} from './application/runtime/conversation-runtime.repository';
import { ConversationRuntimeService } from './application/runtime/conversation-runtime.service';
import { ExecuteConversationTurnService } from './application/runtime/execute-conversation-turn.service';
import { ConversationAccessService } from './application/services/conversation-access.service';
import { CreateConversationSessionService } from './application/services/create-conversation-session.service';
import { ConversationHandoffPolicyService } from './application/services/conversation-handoff-policy.service';
import { InternalAiConversationTransport } from './infrastructure/ai/internal-ai-conversation.transport';
import { PrismaConversationRuntimeRepository } from './infrastructure/persistence/prisma-conversation-runtime.repository';
import { PrismaConversationSessionRepository } from './infrastructure/persistence/prisma-conversation-session.repository';
import { RedisConversationEventReplayBuffer } from './infrastructure/cache/redis-conversation-event-replay-buffer';
import { RedisConversationEventStreamRegistry } from './infrastructure/cache/redis-conversation-event-stream-registry';
import { PrismaActiveAssistantReleaseProjection } from './infrastructure/persistence/prisma-active-assistant-release-projection';
import { ConversationTurnDispatcher } from './infrastructure/runtime/conversation-turn-dispatcher';
import {
  SystemConversationRuntimeClock,
  UuidConversationRuntimeIdGenerator,
} from './infrastructure/runtime/system-conversation-runtime-support';

@Module({
  exports: [
    ConversationAccessService,
    ConversationRuntimeService,
    ConversationTurnDispatcher,
    CreateConversationSessionService,
    ConversationHandoffPolicyService,
    ConversationSessionRepository,
    ConversationEventReplayBuffer,
    ConversationEventStreamRegistry,
    ActiveAssistantReleaseProjection,
  ],
  imports: [
    ConversationContentProtectionModule,
    DatabaseModule,
    InternalAiTrustModule,
    RedisModule,
  ],
  providers: [
    ConversationAccessService,
    ConversationRuntimeService,
    ConversationTurnDispatcher,
    CreateConversationSessionService,
    ConversationHandoffPolicyService,
    ExecuteConversationTurnService,
    {
      provide: ConversationAiTransport,
      useClass: InternalAiConversationTransport,
    },
    {
      provide: ConversationSessionRepository,
      useClass: PrismaConversationSessionRepository,
    },
    {
      provide: ConversationRuntimeRepository,
      useClass: PrismaConversationRuntimeRepository,
    },
    {
      provide: ConversationRuntimeClock,
      useClass: SystemConversationRuntimeClock,
    },
    {
      provide: ConversationRuntimeIdGenerator,
      useClass: UuidConversationRuntimeIdGenerator,
    },
    {
      provide: ConversationEventReplayBuffer,
      useClass: RedisConversationEventReplayBuffer,
    },
    {
      provide: ConversationEventStreamRegistry,
      useClass: RedisConversationEventStreamRegistry,
    },
    {
      provide: ActiveAssistantReleaseProjection,
      useClass: PrismaActiveAssistantReleaseProjection,
    },
  ],
})
export class EngagementRuntimeModule {}
