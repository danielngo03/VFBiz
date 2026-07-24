import { Module } from '@nestjs/common';
import { DatabaseModule } from '../../platform/database/database.module';
import { ConversationSessionRepository } from './application/ports/conversation-session.repository';
import { ConversationAccessService } from './application/services/conversation-access.service';
import { CreateConversationSessionService } from './application/services/create-conversation-session.service';
import { PrismaConversationSessionRepository } from './infrastructure/persistence/prisma-conversation-session.repository';
import { ConversationController } from './presentation/conversation.controller';
import { ConversationAccessGuard } from './presentation/guards/conversation-access.guard';

@Module({
  controllers: [ConversationController],
  imports: [DatabaseModule],
  providers: [
    ConversationAccessService,
    ConversationAccessGuard,
    CreateConversationSessionService,
    {
      provide: ConversationSessionRepository,
      useClass: PrismaConversationSessionRepository,
    },
  ],
})
export class EngagementModule {}
