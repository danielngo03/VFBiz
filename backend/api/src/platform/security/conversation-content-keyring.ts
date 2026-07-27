import { createSecretKey, type KeyObject } from 'node:crypto';

const KEY_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/;
const AES_256_KEY_BASE64_PATTERN = /^[A-Za-z0-9+/]{43}=$/;

export interface ConversationContentKeyring {
  readonly activeKeyId: string;
  readonly keys: ReadonlyMap<string, KeyObject>;
}

export class ConversationContentKeyringConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ConversationContentKeyringConfigurationError';
  }
}

export function parseConversationContentKeyring(
  activeKeyId: string,
  serializedKeyring: string,
): ConversationContentKeyring {
  if (!KEY_ID_PATTERN.test(activeKeyId)) {
    throw configurationError('active key id is invalid');
  }

  const parsed = parseJson(serializedKeyring);
  assertExactKeys(parsed, ['keys'], 'keyring');
  if (!Array.isArray(parsed.keys) || parsed.keys.length === 0) {
    throw configurationError('keyring must contain at least one key');
  }

  const keys = new Map<string, KeyObject>();
  const uniqueMaterials = new Set<string>();
  for (const candidate of parsed.keys) {
    assertExactKeys(candidate, ['id', 'material'], 'key entry');
    const id = candidate.id;
    const material = candidate.material;
    if (typeof id !== 'string' || !KEY_ID_PATTERN.test(id)) {
      throw configurationError('key entry id is invalid');
    }
    if (keys.has(id)) {
      throw configurationError(`keyring contains duplicate key id "${id}"`);
    }
    if (
      typeof material !== 'string' ||
      !AES_256_KEY_BASE64_PATTERN.test(material)
    ) {
      throw configurationError(
        `key "${id}" material must be canonical Base64 for 32 bytes`,
      );
    }
    if (uniqueMaterials.has(material)) {
      throw configurationError('keyring contains duplicate key material');
    }
    uniqueMaterials.add(material);

    const keyBytes = Buffer.from(material, 'base64');
    if (keyBytes.length !== 32 || keyBytes.toString('base64') !== material) {
      keyBytes.fill(0);
      throw configurationError(`key "${id}" material must contain 32 bytes`);
    }
    keys.set(id, createSecretKey(keyBytes));
    keyBytes.fill(0);
  }

  if (!keys.has(activeKeyId)) {
    throw configurationError('active key id is not present in the keyring');
  }

  return Object.freeze({
    activeKeyId,
    keys,
  });
}

function parseJson(serializedKeyring: string): Record<string, unknown> {
  try {
    const value: unknown = JSON.parse(serializedKeyring);
    if (!isRecord(value)) throw configurationError('keyring must be an object');
    return value;
  } catch (error) {
    if (error instanceof ConversationContentKeyringConfigurationError) {
      throw error;
    }
    throw configurationError('keyring must be valid JSON');
  }
}

function assertExactKeys(
  value: unknown,
  allowedKeys: readonly string[],
  label: string,
): asserts value is Record<string, unknown> {
  if (!isRecord(value)) throw configurationError(`${label} must be an object`);
  const actualKeys = Object.keys(value);
  if (
    actualKeys.length !== allowedKeys.length ||
    actualKeys.some((key) => !allowedKeys.includes(key))
  ) {
    throw configurationError(`${label} contains unknown or missing fields`);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

function configurationError(
  message: string,
): ConversationContentKeyringConfigurationError {
  return new ConversationContentKeyringConfigurationError(
    `Invalid conversation content keyring: ${message}`,
  );
}
