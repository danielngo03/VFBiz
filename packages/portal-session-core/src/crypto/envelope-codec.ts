import "server-only";
import {
  createCipheriv,
  createDecipheriv,
  randomBytes,
} from "node:crypto";
import type { VaultKeyring } from "../contracts";

const VERSION = "v1";

export interface EnvelopeContext {
  readonly namespace: string;
  readonly recordId: string;
  readonly recordType: string;
}

function aad(context: EnvelopeContext): Buffer {
  return Buffer.from(
    JSON.stringify([
      VERSION,
      context.namespace,
      context.recordType,
      context.recordId,
    ]),
    "utf8",
  );
}

function assertAes256Key(value: Buffer | undefined, keyId: string): Buffer {
  if (value === undefined) throw new Error(`Unknown vault key: ${keyId}`);
  if (value.byteLength !== 32)
    throw new Error(`Vault key ${keyId} must be exactly 32 bytes.`);
  return value;
}

export class EnvelopeCodec {
  public constructor(private readonly keyring: VaultKeyring) {}

  public seal(value: unknown, context: EnvelopeContext): string {
    const keyId = this.keyring.activeKeyId;
    if (!/^[A-Za-z0-9_-]{1,64}$/u.test(keyId))
      throw new Error("Invalid active vault key id.");
    const key = assertAes256Key(this.keyring.key(keyId), keyId);
    const initializationVector = randomBytes(12);
    const cipher = createCipheriv("aes-256-gcm", key, initializationVector);
    cipher.setAAD(aad(context));
    const ciphertext = Buffer.concat([
      cipher.update(JSON.stringify(value), "utf8"),
      cipher.final(),
    ]);
    return [
      VERSION,
      keyId,
      initializationVector.toString("base64url"),
      cipher.getAuthTag().toString("base64url"),
      ciphertext.toString("base64url"),
    ].join(".");
  }

  public open<T>(
    encoded: string,
    context: EnvelopeContext,
    options: { readonly legacyKey?: Buffer } = {},
  ): { readonly keyId: string; readonly legacy: boolean; readonly value: T } {
    const parts = encoded.split(".");
    if (parts[0] === VERSION && parts.length === 5) {
      const [, keyId, iv, tag, ciphertext] = parts;
      if (!keyId || !iv || !tag || !ciphertext)
        throw new Error("Invalid vault envelope.");
      const key = assertAes256Key(this.keyring.key(keyId), keyId);
      const decipher = createDecipheriv(
        "aes-256-gcm",
        key,
        Buffer.from(iv, "base64url"),
      );
      decipher.setAAD(aad(context));
      decipher.setAuthTag(Buffer.from(tag, "base64url"));
      return {
        keyId,
        legacy: false,
        value: JSON.parse(
          Buffer.concat([
            decipher.update(Buffer.from(ciphertext, "base64url")),
            decipher.final(),
          ]).toString("utf8"),
        ) as T,
      };
    }

    if (parts.length === 3 && options.legacyKey !== undefined) {
      const [iv, tag, ciphertext] = parts;
      if (!iv || !tag || !ciphertext)
        throw new Error("Invalid legacy vault envelope.");
      const key = assertAes256Key(options.legacyKey, "legacy");
      const decipher = createDecipheriv(
        "aes-256-gcm",
        key,
        Buffer.from(iv, "base64url"),
      );
      decipher.setAuthTag(Buffer.from(tag, "base64url"));
      return {
        keyId: "legacy",
        legacy: true,
        value: JSON.parse(
          Buffer.concat([
            decipher.update(Buffer.from(ciphertext, "base64url")),
            decipher.final(),
          ]).toString("utf8"),
        ) as T,
      };
    }
    throw new Error("Unsupported vault envelope.");
  }
}
