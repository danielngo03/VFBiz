import { createCipheriv, createDecipheriv, randomBytes } from 'node:crypto';
import type { ConversationContentKeyring } from './conversation-content-keyring';

const ALGORITHM = 'aes-256-gcm';
const ENVELOPE_ALGORITHM = 'A256GCM';
const NONCE_BYTES = 12;
const AUTH_TAG_BYTES = 16;
const MAX_CONTENT_BYTES = 64 * 1024;
const MAX_CONTEXT_VALUE_BYTES = 512;
const MAX_ASSOCIATED_DATA_BYTES = 4 * 1024;
const MAX_CIPHERTEXT_BASE64URL_LENGTH = Math.ceil((MAX_CONTENT_BYTES * 4) / 3);
const BASE64URL_PATTERN = /^[A-Za-z0-9_-]*$/;
const KEY_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/;
const ENVELOPE_FIELDS = [
  'version',
  'algorithm',
  'aadVersion',
  'keyId',
  'nonce',
  'ciphertext',
  'tag',
] as const;

export interface ConversationContentProtectionContextV1 {
  readonly version: 1;
  readonly securityDomain: string;
  readonly ownerId: string;
  readonly aggregateId: string;
  readonly recordId: string;
  readonly field: string;
}

export interface ConversationContentEnvelopeV1 {
  readonly version: 1;
  readonly algorithm: 'A256GCM';
  readonly aadVersion: 1;
  readonly keyId: string;
  readonly nonce: string;
  readonly ciphertext: string;
  readonly tag: string;
}

export class ConversationContentProtectionUnavailableError extends Error {
  constructor() {
    super('Conversation content protection is not configured');
    this.name = 'ConversationContentProtectionUnavailableError';
  }
}

export class InvalidConversationContentEnvelopeError extends Error {
  constructor(message = 'Conversation content envelope is invalid') {
    super(message);
    this.name = 'InvalidConversationContentEnvelopeError';
  }
}

export class InvalidConversationContentContextError extends Error {
  constructor() {
    super('Conversation content protection context is invalid');
    this.name = 'InvalidConversationContentContextError';
  }
}

export class ConversationContentSizeLimitError extends Error {
  constructor() {
    super('Conversation content exceeds the protection size limit');
    this.name = 'ConversationContentSizeLimitError';
  }
}

export class UnknownConversationContentKeyError extends Error {
  constructor() {
    super('Conversation content envelope references an unavailable key');
    this.name = 'UnknownConversationContentKeyError';
  }
}

export class ConversationContentAuthenticationError extends Error {
  constructor() {
    super('Conversation content authentication failed');
    this.name = 'ConversationContentAuthenticationError';
  }
}

export class ConversationContentCipher {
  constructor(private readonly keyring?: ConversationContentKeyring) {}

  encrypt(
    plaintext: string,
    context: ConversationContentProtectionContextV1,
  ): ConversationContentEnvelopeV1 {
    const keyring = this.requireKeyring();
    assertContext(context);
    if (Buffer.byteLength(plaintext, 'utf8') > MAX_CONTENT_BYTES) {
      throw new ConversationContentSizeLimitError();
    }
    const activeKey = keyring.keys.get(keyring.activeKeyId);
    if (!activeKey) throw new ConversationContentProtectionUnavailableError();

    const header = {
      version: 1,
      algorithm: ENVELOPE_ALGORITHM,
      aadVersion: 1,
      keyId: keyring.activeKeyId,
    } as const;
    const nonce = randomBytes(NONCE_BYTES);
    const cipher = createCipheriv(ALGORITHM, activeKey, nonce, {
      authTagLength: AUTH_TAG_BYTES,
    });
    cipher.setAAD(buildAssociatedData(header, context));
    const ciphertext = Buffer.concat([
      cipher.update(plaintext, 'utf8'),
      cipher.final(),
    ]);
    const tag = cipher.getAuthTag();

    return Object.freeze({
      ...header,
      nonce: nonce.toString('base64url'),
      ciphertext: ciphertext.toString('base64url'),
      tag: tag.toString('base64url'),
    });
  }

  decrypt(
    candidate: unknown,
    context: ConversationContentProtectionContextV1,
  ): string {
    const keyring = this.requireKeyring();
    assertContext(context);
    const envelope = decodeEnvelope(candidate);
    const key = keyring.keys.get(envelope.keyId);
    if (!key) throw new UnknownConversationContentKeyError();

    const nonce = decodeCanonicalBase64Url(envelope.nonce, NONCE_BYTES);
    const tag = decodeCanonicalBase64Url(envelope.tag, AUTH_TAG_BYTES);
    const ciphertext = decodeCanonicalBase64Url(
      envelope.ciphertext,
      undefined,
      MAX_CONTENT_BYTES,
    );

    try {
      const decipher = createDecipheriv(ALGORITHM, key, nonce, {
        authTagLength: AUTH_TAG_BYTES,
      });
      decipher.setAAD(buildAssociatedData(envelope, context));
      decipher.setAuthTag(tag);
      return Buffer.concat([
        decipher.update(ciphertext),
        decipher.final(),
      ]).toString('utf8');
    } catch {
      throw new ConversationContentAuthenticationError();
    }
  }

  private requireKeyring(): ConversationContentKeyring {
    if (!this.keyring) {
      throw new ConversationContentProtectionUnavailableError();
    }
    return this.keyring;
  }
}

export function decodeConversationContentEnvelope(
  candidate: unknown,
): ConversationContentEnvelopeV1 {
  return decodeEnvelope(candidate);
}

function decodeEnvelope(candidate: unknown): ConversationContentEnvelopeV1 {
  if (!isRecord(candidate)) throw new InvalidConversationContentEnvelopeError();
  const keys = Object.keys(candidate);
  if (
    keys.length !== ENVELOPE_FIELDS.length ||
    keys.some(
      (key) =>
        !ENVELOPE_FIELDS.includes(key as (typeof ENVELOPE_FIELDS)[number]),
    ) ||
    candidate.version !== 1 ||
    candidate.algorithm !== ENVELOPE_ALGORITHM ||
    candidate.aadVersion !== 1 ||
    typeof candidate.keyId !== 'string' ||
    !KEY_ID_PATTERN.test(candidate.keyId) ||
    typeof candidate.nonce !== 'string' ||
    typeof candidate.ciphertext !== 'string' ||
    typeof candidate.tag !== 'string' ||
    candidate.ciphertext.length > MAX_CIPHERTEXT_BASE64URL_LENGTH
  ) {
    throw new InvalidConversationContentEnvelopeError();
  }
  decodeCanonicalBase64Url(candidate.nonce, NONCE_BYTES);
  decodeCanonicalBase64Url(candidate.tag, AUTH_TAG_BYTES);
  decodeCanonicalBase64Url(candidate.ciphertext, undefined, MAX_CONTENT_BYTES);
  return candidate as unknown as ConversationContentEnvelopeV1;
}

function assertContext(context: ConversationContentProtectionContextV1): void {
  if (
    typeof context !== 'object' ||
    context === null ||
    context.version !== 1 ||
    !isBoundedContextValue(context.securityDomain) ||
    !isBoundedContextValue(context.ownerId) ||
    !isBoundedContextValue(context.aggregateId) ||
    !isBoundedContextValue(context.recordId) ||
    !isBoundedContextValue(context.field)
  ) {
    throw new InvalidConversationContentContextError();
  }
}

function buildAssociatedData(
  header: Pick<
    ConversationContentEnvelopeV1,
    'version' | 'algorithm' | 'aadVersion' | 'keyId'
  >,
  context: ConversationContentProtectionContextV1,
): Buffer {
  const encoded = Buffer.from(
    JSON.stringify([
      header.version,
      header.algorithm,
      header.aadVersion,
      header.keyId,
      context.version,
      context.securityDomain,
      context.ownerId,
      context.aggregateId,
      context.recordId,
      context.field,
    ]),
    'utf8',
  );
  if (encoded.length > MAX_ASSOCIATED_DATA_BYTES) {
    throw new InvalidConversationContentContextError();
  }
  return encoded;
}

function isBoundedContextValue(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.length > 0 &&
    Buffer.byteLength(value, 'utf8') <= MAX_CONTEXT_VALUE_BYTES
  );
}

function decodeCanonicalBase64Url(
  value: string,
  expectedBytes?: number,
  maximumBytes?: number,
): Buffer {
  if (
    !BASE64URL_PATTERN.test(value) ||
    (expectedBytes !== undefined &&
      value.length !== Math.ceil((expectedBytes * 4) / 3)) ||
    (maximumBytes !== undefined &&
      value.length > Math.ceil((maximumBytes * 4) / 3))
  ) {
    throw new InvalidConversationContentEnvelopeError();
  }
  const decoded = Buffer.from(value, 'base64url');
  if (
    decoded.toString('base64url') !== value ||
    (expectedBytes !== undefined && decoded.length !== expectedBytes) ||
    (maximumBytes !== undefined && decoded.length > maximumBytes)
  ) {
    throw new InvalidConversationContentEnvelopeError();
  }
  return decoded;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
