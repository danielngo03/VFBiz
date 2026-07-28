import {
  createHash,
  createPublicKey,
  timingSafeEqual,
  verify,
  type KeyObject,
} from 'node:crypto';
import { readFileSync } from 'node:fs';
import type { InternalAiResponseVerificationKeyReference } from '../../../../platform/config/internal-ai-trust.config';
import { ConversationAiTransportError } from '../../application/runtime/conversation-ai.transport';

const CONTEXT = 'VFBIZ-AI-RESPONSE-V1';
const CLOCK_SKEW_MS = 5_000;
const MAX_TTL_MS = 60_000;
const SHA_256_PATTERN = /^[a-f0-9]{64}$/;

export class InternalAiResponseVerifier {
  private readonly keys: ReadonlyMap<string, KeyObject>;

  constructor(
    references: readonly InternalAiResponseVerificationKeyReference[],
  ) {
    this.keys = new Map(
      references.map((reference) => {
        const key = createPublicKey(readFileSync(reference.publicKeyFile));
        if (key.asymmetricKeyType !== 'ed25519') {
          throw new Error(
            'Internal AI response verification key must be Ed25519',
          );
        }
        return [reference.kid, key];
      }),
    );
  }

  get enabled(): boolean {
    return this.keys.size > 0;
  }

  verify(input: {
    body: Uint8Array;
    correlationId: string;
    headers: Headers;
    requestId: string;
    now?: Date;
  }): void {
    const keyId = requiredHeader(input.headers, 'x-vfbiz-ai-response-key-id');
    const issuedAt = requiredHeader(
      input.headers,
      'x-vfbiz-ai-response-issued-at',
    );
    const expiresAt = requiredHeader(
      input.headers,
      'x-vfbiz-ai-response-expires-at',
    );
    const bodySha256 = requiredHeader(
      input.headers,
      'x-vfbiz-ai-response-body-sha256',
    );
    const encodedSignature = requiredHeader(
      input.headers,
      'x-vfbiz-ai-response-signature',
    );
    const key = this.keys.get(keyId);
    if (key === undefined || !SHA_256_PATTERN.test(bodySha256)) fail();
    const actualDigest = createHash('sha256').update(input.body).digest('hex');
    if (!safeEqual(bodySha256, actualDigest)) fail();

    const issued = parseTimestamp(issuedAt);
    const expires = parseTimestamp(expiresAt);
    const now = (input.now ?? new Date()).getTime();
    if (
      issued > now + CLOCK_SKEW_MS ||
      expires < now - CLOCK_SKEW_MS ||
      expires <= issued ||
      expires - issued > MAX_TTL_MS
    ) {
      fail();
    }
    let signature: Buffer;
    try {
      signature = Buffer.from(encodedSignature, 'base64url');
    } catch {
      fail();
    }
    const canonical = Buffer.from(
      `${CONTEXT}\n${keyId}\n${issuedAt}\n${expiresAt}\n${input.requestId}\n${input.correlationId}\n${bodySha256}`,
      'utf8',
    );
    if (!verify(null, canonical, key, signature)) fail();
  }
}

function requiredHeader(headers: Headers, name: string): string {
  const value = headers.get(name);
  if (value === null || value.length === 0 || value.length > 512) fail();
  return value;
}

function parseTimestamp(value: string): number {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) fail();
  return parsed;
}

function safeEqual(left: string, right: string): boolean {
  const leftBytes = Buffer.from(left, 'ascii');
  const rightBytes = Buffer.from(right, 'ascii');
  return (
    leftBytes.length === rightBytes.length &&
    timingSafeEqual(leftBytes, rightBytes)
  );
}

function fail(): never {
  throw new ConversationAiTransportError('invalid_response', false);
}
