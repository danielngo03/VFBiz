import { ConfigService } from '@nestjs/config';
import type { EnvironmentVariables } from '../config/env.schema';
import { ConversationContentCipher } from './conversation-content-cipher';
import { parseConversationContentKeyring } from './conversation-content-keyring';

export function createConversationContentCipher(
  config: ConfigService<EnvironmentVariables, true>,
): ConversationContentCipher {
  const runtimeEnvironment = config.get('NODE_ENV', { infer: true });
  const activeKeyId = config.get('VFBIZ_CONVERSATION_CONTENT_ACTIVE_KEY_ID', {
    infer: true,
  });
  const serializedKeyring = config.get('VFBIZ_CONVERSATION_CONTENT_KEYRING', {
    infer: true,
  });

  if (activeKeyId === undefined || serializedKeyring === undefined) {
    if (
      runtimeEnvironment === 'staging' ||
      runtimeEnvironment === 'production'
    ) {
      throw new Error(
        'Conversation content protection is required in staging and production',
      );
    }
    return new ConversationContentCipher();
  }

  return new ConversationContentCipher(
    parseConversationContentKeyring(activeKeyId, serializedKeyring),
  );
}
