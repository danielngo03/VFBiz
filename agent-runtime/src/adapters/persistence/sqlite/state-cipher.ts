import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";
import { RuntimeError } from "../../../domain/errors.js";

export interface EncryptedState {
  ciphertext: string;
  digest: string;
}

export class StateCipher {
  private readonly key: Buffer;

  public constructor(encodedKey = process.env.VFBIZ_AGENT_RUNTIME_STATE_KEY) {
    if (!encodedKey) {
      throw new RuntimeError(
        "STATE_KEY_MISSING",
        "VFBIZ_AGENT_RUNTIME_STATE_KEY is required for prompt-bearing checkpoints",
      );
    }
    this.key = Buffer.from(encodedKey, "base64");
    if (this.key.length !== 32) {
      throw new RuntimeError(
        "STATE_KEY_INVALID",
        "VFBIZ_AGENT_RUNTIME_STATE_KEY must be a base64-encoded 32-byte key",
      );
    }
  }

  public encrypt(plaintext: string): EncryptedState {
    const iv = randomBytes(12);
    const cipher = createCipheriv("aes-256-gcm", this.key, iv);
    const encrypted = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
    const tag = cipher.getAuthTag();
    return {
      ciphertext: ["v1", iv.toString("base64"), tag.toString("base64"), encrypted.toString("base64")].join(":"),
      digest: createHash("sha256").update(plaintext).digest("hex"),
    };
  }

  public decrypt(value: string): string {
    const [version, encodedIv, encodedTag, encodedCiphertext] = value.split(":");
    if (version !== "v1" || !encodedIv || !encodedTag || !encodedCiphertext) {
      throw new RuntimeError("STATE_CIPHERTEXT_INVALID", "encrypted runtime state is malformed");
    }
    try {
      const decipher = createDecipheriv("aes-256-gcm", this.key, Buffer.from(encodedIv, "base64"));
      decipher.setAuthTag(Buffer.from(encodedTag, "base64"));
      return Buffer.concat([
        decipher.update(Buffer.from(encodedCiphertext, "base64")),
        decipher.final(),
      ]).toString("utf8");
    } catch {
      throw new RuntimeError("STATE_DECRYPTION_FAILED", "encrypted runtime state failed authentication");
    }
  }
}
