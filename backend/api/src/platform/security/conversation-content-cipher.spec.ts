import {
  ConversationContentAuthenticationError,
  ConversationContentCipher,
  ConversationContentProtectionUnavailableError,
  ConversationContentSizeLimitError,
  decodeConversationContentEnvelope,
  InvalidConversationContentEnvelopeError,
  UnknownConversationContentKeyError,
  type ConversationContentProtectionContextV1,
  type ConversationContentEnvelopeV1,
} from './conversation-content-cipher';
import {
  ConversationContentKeyringConfigurationError,
  parseConversationContentKeyring,
} from './conversation-content-keyring';

const oldKey = Buffer.alloc(32, 1).toString('base64');
const activeKey = Buffer.alloc(32, 2).toString('base64');

function keyring(activeKeyId = 'key-2026-02') {
  return parseConversationContentKeyring(
    activeKeyId,
    JSON.stringify({
      keys: [
        { id: 'key-2026-01', material: oldKey },
        { id: 'key-2026-02', material: activeKey },
      ],
    }),
  );
}

const protectionContext: ConversationContentProtectionContextV1 = {
  version: 1,
  securityDomain: 'vfbiz-customer',
  ownerId: 'synthetic-owner',
  aggregateId: 'synthetic-conversation',
  recordId: 'synthetic-turn',
  field: 'customer-message',
};

describe('ConversationContentCipher', () => {
  it('encrypts with the active key and authenticates caller-provided context', () => {
    const cipher = new ConversationContentCipher(keyring());

    const envelope = cipher.encrypt(
      'synthetic customer message',
      protectionContext,
    );

    expect(envelope).toMatchObject({
      version: 1,
      algorithm: 'A256GCM',
      aadVersion: 1,
      keyId: 'key-2026-02',
    });
    expect(cipher.decrypt(envelope, protectionContext)).toBe(
      'synthetic customer message',
    );
  });

  it('decrypts an old envelope after active-key rotation', () => {
    const oldCipher = new ConversationContentCipher(keyring('key-2026-01'));
    const envelope = oldCipher.encrypt(
      'synthetic old message',
      protectionContext,
    );
    const rotatedCipher = new ConversationContentCipher(keyring());

    expect(rotatedCipher.decrypt(envelope, protectionContext)).toBe(
      'synthetic old message',
    );
    expect(rotatedCipher.encrypt('new message', protectionContext).keyId).toBe(
      'key-2026-02',
    );
  });

  it.each(['ciphertext', 'tag', 'nonce'] as const)(
    'rejects a tampered %s without disclosing content',
    (field) => {
      const cipher = new ConversationContentCipher(keyring());
      const envelope = cipher.encrypt('synthetic message', protectionContext);
      const tampered = {
        ...envelope,
        [field]: replaceFirstCharacter(envelope[field]),
      };

      expect(() => cipher.decrypt(tampered, protectionContext)).toThrow(
        ConversationContentAuthenticationError,
      );
    },
  );

  it('rejects the wrong associated data', () => {
    const cipher = new ConversationContentCipher(keyring());
    const envelope = cipher.encrypt('synthetic message', protectionContext);

    expect(() =>
      cipher.decrypt(envelope, {
        ...protectionContext,
        recordId: 'different-turn',
      }),
    ).toThrow(ConversationContentAuthenticationError);
  });

  it('authenticates the key id even when two configured ids alias one key', () => {
    const material = Buffer.alloc(32, 9).toString('base64');
    const aliasKeyring = parseConversationContentKeyring(
      'key-alias-a',
      JSON.stringify({
        keys: [{ id: 'key-alias-a', material }],
      }),
    );
    const key = aliasKeyring.keys.get('key-alias-a')!;
    const cipher = new ConversationContentCipher(aliasKeyring);
    const envelope = cipher.encrypt('synthetic message', protectionContext);
    const decryptingCipher = new ConversationContentCipher({
      activeKeyId: 'key-alias-b',
      keys: new Map([
        ['key-alias-a', key],
        ['key-alias-b', key],
      ]),
    });

    expect(() =>
      decryptingCipher.decrypt(
        { ...envelope, keyId: 'key-alias-b' },
        protectionContext,
      ),
    ).toThrow(ConversationContentAuthenticationError);
  });

  it('rejects an unknown key without trying another key', () => {
    const cipher = new ConversationContentCipher(keyring());
    const envelope = cipher.encrypt('synthetic message', protectionContext);

    expect(() =>
      cipher.decrypt({ ...envelope, keyId: 'unknown-key' }, protectionContext),
    ).toThrow(UnknownConversationContentKeyError);
  });

  it('rejects malformed envelopes and empty associated data', () => {
    const cipher = new ConversationContentCipher(keyring());
    const malformed = {
      version: 1,
      algorithm: 'A256GCM',
      aadVersion: 1,
      keyId: 'key-2026-02',
      nonce: 'not+base64url',
      ciphertext: '',
      tag: '',
    } as ConversationContentEnvelopeV1;

    expect(() => cipher.decrypt(malformed, protectionContext)).toThrow(
      InvalidConversationContentEnvelopeError,
    );
    expect(() =>
      cipher.encrypt('synthetic message', {
        ...protectionContext,
        field: '',
      }),
    ).toThrow('Conversation content protection context is invalid');
  });

  it('rejects unknown envelope fields and oversized content before decoding', () => {
    const cipher = new ConversationContentCipher(keyring());
    const envelope = cipher.encrypt('synthetic message', protectionContext);

    expect(() =>
      cipher.decrypt({ ...envelope, unexpected: true }, protectionContext),
    ).toThrow(InvalidConversationContentEnvelopeError);
    expect(() =>
      cipher.encrypt('x'.repeat(64 * 1024 + 1), protectionContext),
    ).toThrow(ConversationContentSizeLimitError);
    expect(() =>
      cipher.decrypt(
        {
          ...envelope,
          ciphertext: 'A'.repeat(Math.ceil(((64 * 1024 + 1) * 4) / 3)),
        },
        protectionContext,
      ),
    ).toThrow(InvalidConversationContentEnvelopeError);
  });

  it.each(['nonce', 'tag'] as const)(
    'rejects an oversized %s at the envelope trust boundary',
    (field) => {
      const cipher = new ConversationContentCipher(keyring());
      const envelope = cipher.encrypt('synthetic message', protectionContext);
      const oversized = { ...envelope, [field]: 'A'.repeat(1024 * 1024) };

      expect(() => decodeConversationContentEnvelope(oversized)).toThrow(
        InvalidConversationContentEnvelopeError,
      );
      expect(() => cipher.decrypt(oversized, protectionContext)).toThrow(
        InvalidConversationContentEnvelopeError,
      );
    },
  );

  it('rejects noncanonical encoded fields at the envelope trust boundary', () => {
    const cipher = new ConversationContentCipher(keyring());
    const envelope = cipher.encrypt('synthetic message', protectionContext);

    expect(() =>
      decodeConversationContentEnvelope({
        ...envelope,
        ciphertext: `${envelope.ciphertext}=`,
      }),
    ).toThrow(InvalidConversationContentEnvelopeError);
  });

  it('fails closed when content protection is unavailable', () => {
    const cipher = new ConversationContentCipher();

    expect(() =>
      cipher.encrypt('synthetic message', protectionContext),
    ).toThrow(ConversationContentProtectionUnavailableError);
  });
});

describe('parseConversationContentKeyring', () => {
  it.each([
    [
      'duplicate material',
      JSON.stringify({
        keys: [
          { id: 'key-1', material: oldKey },
          { id: 'key-2', material: oldKey },
        ],
      }),
    ],
    [
      'duplicate ids',
      JSON.stringify({
        keys: [
          { id: 'duplicate', material: oldKey },
          { id: 'duplicate', material: activeKey },
        ],
      }),
    ],
    [
      'weak key material',
      JSON.stringify({ keys: [{ id: 'key-1', material: 'd2Vhaw==' }] }),
    ],
    [
      'unknown fields',
      JSON.stringify({
        keys: [{ id: 'key-1', material: oldKey, purpose: 'unexpected' }],
      }),
    ],
  ])('rejects %s', (_label, serialized) => {
    expect(() => parseConversationContentKeyring('key-1', serialized)).toThrow(
      ConversationContentKeyringConfigurationError,
    );
  });

  it('rejects an active key that is absent from the keyring', () => {
    expect(() =>
      parseConversationContentKeyring(
        'missing-key',
        JSON.stringify({
          keys: [{ id: 'key-1', material: oldKey }],
        }),
      ),
    ).toThrow(ConversationContentKeyringConfigurationError);
  });
});

function replaceFirstCharacter(value: string): string {
  return `${value.startsWith('A') ? 'B' : 'A'}${value.slice(1)}`;
}
