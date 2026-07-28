import { createHash, generateKeyPairSync, sign } from 'node:crypto';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { InternalAiResponseVerifier } from './internal-ai-response-verifier';

const requestId = '323e4567-e89b-42d3-a456-426614174000';
const correlationId = '423e4567-e89b-42d3-a456-426614174000';
const keyId = 'ai-response-current';

describe('InternalAiResponseVerifier', () => {
  const { privateKey, publicKey } = generateKeyPairSync('ed25519');
  const directory = mkdtempSync(join(tmpdir(), 'vfbiz-ai-response-'));
  const publicKeyFile = join(directory, 'public.pem');
  writeFileSync(
    publicKeyFile,
    publicKey.export({ format: 'pem', type: 'spki' }),
    { mode: 0o600 },
  );
  const verifier = new InternalAiResponseVerifier([
    { algorithm: 'EdDSA', kid: keyId, publicKeyFile },
  ]);

  it('accepts a response bound to body, request and correlation', () => {
    const body = Buffer.from('{"outcome":"refused"}', 'utf8');
    const now = new Date('2026-07-27T12:00:10.000Z');
    const headers = signedHeaders(body);

    expect(() =>
      verifier.verify({ body, correlationId, headers, requestId, now }),
    ).not.toThrow();
  });

  it.each([
    [
      'tampered body',
      Buffer.from('{"outcome":"answered"}', 'utf8'),
      correlationId,
    ],
    [
      'wrong correlation',
      Buffer.from('{"outcome":"refused"}', 'utf8'),
      'other',
    ],
  ])('rejects %s', (_name, body, candidateCorrelationId) => {
    expect(() =>
      verifier.verify({
        body,
        correlationId: candidateCorrelationId,
        headers: signedHeaders(Buffer.from('{"outcome":"refused"}', 'utf8')),
        requestId,
        now: new Date('2026-07-27T12:00:10.000Z'),
      }),
    ).toThrow();
  });

  it('rejects an expired signature', () => {
    const body = Buffer.from('{"outcome":"refused"}', 'utf8');
    expect(() =>
      verifier.verify({
        body,
        correlationId,
        headers: signedHeaders(body),
        requestId,
        now: new Date('2026-07-27T12:01:00.000Z'),
      }),
    ).toThrow();
  });

  it('accepts an overlapping rotation key from the allowlisted keyring', () => {
    const next = generateKeyPairSync('ed25519');
    const nextPublicKeyFile = join(directory, 'next-public.pem');
    writeFileSync(
      nextPublicKeyFile,
      next.publicKey.export({ format: 'pem', type: 'spki' }),
      { mode: 0o600 },
    );
    const rotatingVerifier = new InternalAiResponseVerifier([
      { algorithm: 'EdDSA', kid: keyId, publicKeyFile },
      {
        algorithm: 'EdDSA',
        kid: 'ai-response-next',
        publicKeyFile: nextPublicKeyFile,
      },
    ]);
    const body = Buffer.from('{"outcome":"refused"}', 'utf8');
    const issuedAt = '2026-07-27T12:00:00.000Z';
    const expiresAt = '2026-07-27T12:00:30.000Z';
    const bodySha256 = createHash('sha256').update(body).digest('hex');
    const canonical = Buffer.from(
      `VFBIZ-AI-RESPONSE-V1\nai-response-next\n${issuedAt}\n${expiresAt}\n${requestId}\n${correlationId}\n${bodySha256}`,
      'utf8',
    );
    const headers = new Headers({
      'x-vfbiz-ai-response-body-sha256': bodySha256,
      'x-vfbiz-ai-response-expires-at': expiresAt,
      'x-vfbiz-ai-response-issued-at': issuedAt,
      'x-vfbiz-ai-response-key-id': 'ai-response-next',
      'x-vfbiz-ai-response-signature': sign(
        null,
        canonical,
        next.privateKey,
      ).toString('base64url'),
    });

    expect(() =>
      rotatingVerifier.verify({
        body,
        correlationId,
        headers,
        requestId,
        now: new Date('2026-07-27T12:00:10.000Z'),
      }),
    ).not.toThrow();
  });

  function signedHeaders(body: Buffer): Headers {
    const issuedAt = '2026-07-27T12:00:00.000Z';
    const expiresAt = '2026-07-27T12:00:30.000Z';
    const bodySha256 = createHash('sha256').update(body).digest('hex');
    const canonical = Buffer.from(
      `VFBIZ-AI-RESPONSE-V1\n${keyId}\n${issuedAt}\n${expiresAt}\n${requestId}\n${correlationId}\n${bodySha256}`,
      'utf8',
    );
    return new Headers({
      'x-vfbiz-ai-response-body-sha256': bodySha256,
      'x-vfbiz-ai-response-expires-at': expiresAt,
      'x-vfbiz-ai-response-issued-at': issuedAt,
      'x-vfbiz-ai-response-key-id': keyId,
      'x-vfbiz-ai-response-signature': sign(
        null,
        canonical,
        privateKey,
      ).toString('base64url'),
    });
  }
});
