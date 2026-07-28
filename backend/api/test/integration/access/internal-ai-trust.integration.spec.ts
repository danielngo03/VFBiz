import { generateKeyPairSync, randomUUID } from 'node:crypto';
import { chmodSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ConfigModule } from '@nestjs/config';
import { Test, type TestingModule } from '@nestjs/testing';
import { decodeProtectedHeader } from 'jose';
import { InternalAiAssertionSigner } from '../../../src/platform/security/internal-ai-assertion-signer';
import { InternalAiJwksExporter } from '../../../src/platform/security/internal-ai-jwks-exporter';
import { InternalAiTrustModule } from '../../../src/platform/security/internal-ai-trust.module';

describe('InternalAiTrustModule integration', () => {
  const directory = mkdtempSync(join(tmpdir(), 'vfbiz-ai-trust-module-'));
  const privateKeyFile = join(directory, 'api-ai.pem');
  const responsePublicKeyFile = join(directory, 'ai-response-public.pem');
  let module: TestingModule;

  beforeAll(async () => {
    const privateKey = generateKeyPairSync('ec', {
      namedCurve: 'P-256',
    }).privateKey;
    writeFileSync(
      privateKeyFile,
      privateKey.export({ format: 'pem', type: 'pkcs8' }),
      { mode: 0o600 },
    );
    chmodSync(privateKeyFile, 0o600);
    const responsePublicKey = generateKeyPairSync('ed25519').publicKey;
    writeFileSync(
      responsePublicKeyFile,
      responsePublicKey.export({ format: 'pem', type: 'spki' }),
      { mode: 0o600 },
    );

    module = await Test.createTestingModule({
      imports: [
        ConfigModule.forRoot({
          ignoreEnvFile: true,
          isGlobal: true,
          load: [
            () => ({
              VFBIZ_INTERNAL_AI_ENABLED: true,
              VFBIZ_INTERNAL_AI_BASE_URL: 'http://127.0.0.1:8888',
              VFBIZ_INTERNAL_AI_ALLOWED_HOSTS: '127.0.0.1',
              VFBIZ_INTERNAL_AI_REQUEST_TIMEOUT_MS: 15_000,
              VFBIZ_INTERNAL_AI_RETRY_BUDGET: 1,
              VFBIZ_INTERNAL_AI_ASSERTION_ISSUER: 'vfbiz-api',
              VFBIZ_INTERNAL_AI_ASSERTION_AUDIENCE: 'vfbiz-ai',
              VFBIZ_INTERNAL_AI_ASSERTION_TTL_SECONDS: 30,
              VFBIZ_INTERNAL_AI_ASSERTION_ACTIVE_KEY_ID: 'api-ai-current',
              VFBIZ_INTERNAL_AI_ASSERTION_KEYRING: JSON.stringify({
                keys: [
                  {
                    alg: 'ES256',
                    kid: 'api-ai-current',
                    privateKeyFile,
                  },
                ],
              }),
              VFBIZ_INTERNAL_AI_RESPONSE_VERIFICATION_KEYRING: JSON.stringify({
                keys: [
                  {
                    alg: 'EdDSA',
                    kid: 'ai-response-current',
                    publicKeyFile: responsePublicKeyFile,
                  },
                ],
              }),
              VFBIZ_INTERNAL_AI_SUBJECT_PSEUDONYMIZATION_KEY:
                'MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=',
            }),
          ],
        }),
        InternalAiTrustModule,
      ],
    }).compile();
  });

  afterAll(async () => {
    await module.close();
    rmSync(directory, { force: true, recursive: true });
  });

  it('wires signer and public JWKS without exposing private material', async () => {
    const signed = await module.get(InternalAiAssertionSigner).sign({
      action: 'turn.cancel',
      activationId: '00000000-0000-4000-8000-000000000010',
      assistantProfile: 'public_customer',
      authorization: {
        allowedTools: ['search_public_knowledge'],
        capabilityHash: 'c'.repeat(64),
        kind: 'public_capability',
      },
      budget: {
        deadlineAt: new Date(Date.now() + 60_000).toISOString(),
        maxCostMicros: 1,
        maxModelTokens: 1,
      },
      conversationVersion: 1,
      correlationId: randomUUID(),
      fencingToken: 1,
      locale: 'vi',
      graphRevision: 'graph-integration',
      knowledgeRevision: 'knowledge-integration',
      manifestSha256: 'e'.repeat(64),
      policyRevision: 'policy-integration',
      requestHash: 'd'.repeat(64),
      requestId: randomUUID(),
      sessionId: randomUUID(),
      turnId: randomUUID(),
    });
    const jwks = module.get(InternalAiJwksExporter).export();

    expect(decodeProtectedHeader(signed.token)).toMatchObject({
      alg: 'ES256',
      kid: 'api-ai-current',
      typ: 'vfbiz-ai+jwt',
    });
    expect(jwks.keys).toHaveLength(1);
    expect(jwks.keys[0]).not.toHaveProperty('d');
  });
});
