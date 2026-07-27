import { ConfigService } from '@nestjs/config';
import type { EnvironmentVariables } from '../config/env.schema';
import { ConversationContentProtectionUnavailableError } from './conversation-content-cipher';
import { createConversationContentCipher } from './conversation-content-cipher.provider';

const activeKeyId = 'key-2026-01';
const serializedKeyring = JSON.stringify({
  keys: [
    {
      id: activeKeyId,
      material: Buffer.alloc(32, 7).toString('base64'),
    },
  ],
});
const protectionContext = {
  version: 1,
  securityDomain: 'vfbiz-customer',
  ownerId: 'synthetic-owner',
  aggregateId: 'synthetic-conversation',
  recordId: 'synthetic-turn',
  field: 'customer-message',
} as const;

describe('createConversationContentCipher', () => {
  it.each(['staging', 'production'] as const)(
    'fails application startup without a keyring in %s',
    (runtimeEnvironment) => {
      expect(() =>
        createConversationContentCipher(
          configService({ NODE_ENV: runtimeEnvironment }),
        ),
      ).toThrow(
        'Conversation content protection is required in staging and production',
      );
    },
  );

  it('permits local startup but keeps encryption unavailable', () => {
    const cipher = createConversationContentCipher(
      configService({ NODE_ENV: 'development' }),
    );

    expect(() =>
      cipher.encrypt('synthetic message', protectionContext),
    ).toThrow(ConversationContentProtectionUnavailableError);
  });

  it('constructs a configured cipher for production', () => {
    const cipher = createConversationContentCipher(
      configService({
        NODE_ENV: 'production',
        VFBIZ_CONVERSATION_CONTENT_ACTIVE_KEY_ID: activeKeyId,
        VFBIZ_CONVERSATION_CONTENT_KEYRING: serializedKeyring,
      }),
    );

    const envelope = cipher.encrypt('synthetic message', protectionContext);
    expect(cipher.decrypt(envelope, protectionContext)).toBe(
      'synthetic message',
    );
  });
});

function configService(
  values: Partial<EnvironmentVariables>,
): ConfigService<EnvironmentVariables, true> {
  return {
    get: jest.fn((key: keyof EnvironmentVariables) => values[key]),
  } as unknown as ConfigService<EnvironmentVariables, true>;
}
