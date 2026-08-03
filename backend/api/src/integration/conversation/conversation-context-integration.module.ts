import { Global, Module } from '@nestjs/common';
import { ConversationTaskSlotAuthority } from '../../modules/engagement/application/ports/conversation-task-slot-authority';
import { ProductModule } from '../../modules/product/product.module';
import { CatalogConversationTaskSlotAuthority } from './catalog-conversation-task-slot-authority';

/**
 * Explicit composition boundary for cross-context read-only resolution.
 * Business contexts remain unaware of each other's internals.
 */
@Global()
@Module({
  exports: [ConversationTaskSlotAuthority],
  imports: [ProductModule],
  providers: [
    {
      provide: ConversationTaskSlotAuthority,
      useClass: CatalogConversationTaskSlotAuthority,
    },
  ],
})
export class ConversationContextIntegrationModule {}
