import { Module } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { ConversationContentCipher } from './conversation-content-cipher';
import { createConversationContentCipher } from './conversation-content-cipher.provider';

@Module({
  imports: [ConfigModule],
  providers: [
    {
      provide: ConversationContentCipher,
      inject: [ConfigService],
      useFactory: createConversationContentCipher,
    },
  ],
  exports: [ConversationContentCipher],
})
export class ConversationContentProtectionModule {}
