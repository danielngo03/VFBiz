import { Module } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { ThrottlerModule } from '@nestjs/throttler';
import { ConversationContextIntegrationModule } from '../../integration/conversation/conversation-context-integration.module';
import type { EnvironmentVariables } from '../../platform/config/env.schema';
import { RedisConnectionService } from '../../platform/redis/redis-connection.service';
import { RedisModule } from '../../platform/redis/redis.module';
import { RedisThrottlerStorageService } from '../../platform/redis/redis-throttler-storage.service';
import {
  ClosedStagingChatLiveControl,
  StagingChatLiveControl,
} from './application/ports/staging-chat-live-control';
import { ActiveAssistantReleaseProjection } from './application/ports/active-assistant-release-projection';
import { EngagementRuntimeModule } from './engagement-runtime.module';
import { RedisStagingChatLiveControl } from './infrastructure/cache/redis-staging-chat-live-control';
import { ConversationController } from './presentation/conversation.controller';
import { AuthenticatedStagingChatGuard } from './presentation/guards/authenticated-staging-chat.guard';
import { ConversationAccessGuard } from './presentation/guards/conversation-access.guard';
import { ChatThrottlerGuard } from './presentation/guards/chat-throttler.guard';
import { StagingChatLiveControlGuard } from './presentation/guards/staging-chat-live-control.guard';

@Module({
  controllers: [ConversationController],
  imports: [
    ConversationContextIntegrationModule,
    EngagementRuntimeModule,
    RedisModule,
    // Per-route limits are set with @Throttle() on ConversationController.
    // Redis makes the policy consistent across every API instance.
    ThrottlerModule.forRootAsync({
      imports: [RedisModule],
      inject: [RedisThrottlerStorageService],
      useFactory: (storage: RedisThrottlerStorageService) => ({
        storage,
        throttlers: [
          { name: 'default', ttl: 60_000, limit: 30, blockDuration: 60_000 },
        ],
      }),
    }),
  ],
  providers: [
    AuthenticatedStagingChatGuard,
    {
      inject: [
        RedisConnectionService,
        ActiveAssistantReleaseProjection,
        ConfigService,
      ],
      provide: StagingChatLiveControl,
      useFactory: (
        redis: RedisConnectionService,
        releases: ActiveAssistantReleaseProjection,
        config: ConfigService<EnvironmentVariables, true>,
      ) => {
        if (
          config.getOrThrow('VFBIZ_CHAT_API_MODE') !== 'authenticated-staging'
        ) {
          return new ClosedStagingChatLiveControl();
        }
        return new RedisStagingChatLiveControl(redis, releases, {
          authorityDigest: config.getOrThrow(
            'VFBIZ_CHAT_LIVE_CONTROL_AUTHORITY_SHA256',
          ),
          controlId: config.getOrThrow('VFBIZ_CHAT_LIVE_CONTROL_ID'),
          expiresAt: new Date(
            config.getOrThrow('VFBIZ_CHAT_LIVE_CONTROL_EXPIRES_AT'),
          ),
          generation: config.getOrThrow('VFBIZ_CHAT_LIVE_CONTROL_GENERATION'),
          notBefore: new Date(
            config.getOrThrow('VFBIZ_CHAT_LIVE_CONTROL_NOT_BEFORE'),
          ),
          releaseEnvelopeSha256: config.getOrThrow(
            'VFBIZ_CHAT_LIVE_CONTROL_RELEASE_ENVELOPE_SHA256',
          ),
          releasePointerRevision: config.getOrThrow(
            'VFBIZ_CHAT_LIVE_CONTROL_RELEASE_POINTER_REVISION',
          ),
        });
      },
    },
    StagingChatLiveControlGuard,
    ConversationAccessGuard,
    ChatThrottlerGuard,
  ],
})
export class EngagementModule {}
