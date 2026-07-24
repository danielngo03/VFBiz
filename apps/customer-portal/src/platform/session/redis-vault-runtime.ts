import "server-only";
import {
  createCipheriv,
  createDecipheriv,
  createHash,
  randomBytes,
} from "node:crypto";
import Redis from "ioredis";
import { readCustomerPortalEnvironment } from "@/platform/config/environment";

let client: Redis | undefined;

export function customerSessionRedis(): Redis {
  client ??= new Redis(readCustomerPortalEnvironment().CUSTOMER_REDIS_URL, {
    connectTimeout: 2_000,
    enableReadyCheck: true,
    maxRetriesPerRequest: 1,
  });
  return client;
}

export function customerSessionKey(prefix: string, value: string): string {
  return `vfbiz:customer:${prefix}:${createHash("sha256").update(value).digest("hex")}`;
}

function encryptionKey(): Buffer {
  return Buffer.from(
    readCustomerPortalEnvironment().CUSTOMER_TOKEN_VAULT_KEY,
    "base64",
  );
}

export function encryptVaultRecord(value: unknown): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", encryptionKey(), iv);
  const ciphertext = Buffer.concat([
    cipher.update(JSON.stringify(value), "utf8"),
    cipher.final(),
  ]);
  return [
    iv.toString("base64url"),
    cipher.getAuthTag().toString("base64url"),
    ciphertext.toString("base64url"),
  ].join(".");
}

export function decryptVaultRecord<T>(value: string): T {
  const [iv, tag, ciphertext] = value.split(".");
  if (!iv || !tag || !ciphertext) throw new Error("Invalid vault record.");
  const decipher = createDecipheriv(
    "aes-256-gcm",
    encryptionKey(),
    Buffer.from(iv, "base64url"),
  );
  decipher.setAuthTag(Buffer.from(tag, "base64url"));
  return JSON.parse(
    Buffer.concat([
      decipher.update(Buffer.from(ciphertext, "base64url")),
      decipher.final(),
    ]).toString("utf8"),
  ) as T;
}
