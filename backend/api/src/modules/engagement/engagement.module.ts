import { Module } from '@nestjs/common';
import { ThrottlerModule } from '@nestjs/throttler';
import { RedisModule } from '../../platform/redis/redis.module';
import { RedisThrottlerStorageService } from '../../platform/redis/redis-throttler-storage.service';
import { EngagementRuntimeModule } from './engagement-runtime.module';
import { ConversationController } from './presentation/conversation.controller';
import { ConversationAccessGuard } from './presentation/guards/conversation-access.guard';
import { ChatThrottlerGuard } from './presentation/guards/chat-throttler.guard';

@Module({
  controllers: [ConversationController],
  imports: [
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
  providers: [ConversationAccessGuard, ChatThrottlerGuard],
})
export class EngagementModule {}
