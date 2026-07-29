import { generateKeyPairSync, type KeyObject, randomUUID } from 'node:crypto';
import { chmodSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ConfigService } from '@nestjs/config';
import { decodeProtectedHeader, importJWK, jwtVerify } from 'jose';
import type { EnvironmentVariables } from '../config/env.schema';
import { InternalAiTrustConfig } from '../config/internal-ai-trust.config';
import { InternalAiAssertionKeyring } from './internal-ai-assertion-keyring';
import { InternalAiAssertionSigner } from './internal-ai-assertion-signer';
import type { InternalAiExecutionAssertionInput } from './internal-ai-execution-assertion';
import { InternalAiJwksExporter } from './internal-ai-jwks-exporter';

describe('InternalAiAssertionSigner', () => {
  const directory = mkdtempSync(join(tmpdir(), 'vfbiz-api-ai-trust-'));
  const es256KeyFile = join(directory, 'es256.pem');
  const edDsaKeyFile = join(directory, 'eddsa.pem');
  const responsePublicKeyFile = join(directory, 'response-public.pem');

  beforeAll(() => {
    writePrivateKey(
      es256KeyFile,
      generateKeyPairSync('ec', { namedCurve: 'P-256' }).privateKey,
    );
    const responseKeyPair = generateKeyPairSync('ed25519');
    writePrivateKey(edDsaKeyFile, responseKeyPair.privateKey);
    writeFileSync(
      responsePublicKeyFile,
      responseKeyPair.publicKey.export({ format: 'pem', type: 'spki' }),
      { mode: 0o600 },
    );
  });

  afterAll(() => {
    rmSync(directory, { force: true, recursive: true });
  });

  it('signs pinned ES256 claims and exports only overlapping public keys', async () => {
    const config = trustConfig('api-ai-current');
    const keyring = new InternalAiAssertionKeyring(config);
    const signer = new InternalAiAssertionSigner(config, keyring);
    const exported = new InternalAiJwksExporter(keyring).export();

    const signed = await signer.sign(validInput());
    const header = decodeProtectedHeader(signed.token);
    expect(header).toEqual({
      alg: 'ES256',
      kid: 'api-ai-current',
      typ: 'vfbiz-ai+jwt',
    });
    expect(exported.keys.map(({ kid }) => kid)).toEqual([
      'api-ai-current',
      'api-ai-next',
    ]);
    for (const jwk of exported.keys) {
      expect(jwk).not.toHaveProperty('d');
      expect(jwk).not.toHaveProperty('p');
      expect(jwk).not.toHaveProperty('q');
      expect(jwk).not.toHaveProperty('k');
      expect(jwk.key_ops).toEqual(['verify']);
    }

    const current = exported.keys.find(({ kid }) => kid === 'api-ai-current');
    expect(current).toBeDefined();
    const verificationKey = await importJWK(
      { ...current!, key_ops: [...current!.key_ops] },
      'ES256',
    );
    const { payload } = await jwtVerify(signed.token, verificationKey, {
      algorithms: ['ES256'],
      audience: 'vfbiz-ai',
      issuer: 'vfbiz-api',
      requiredClaims: ['exp', 'iat', 'nbf', 'jti'],
    });
    expect(payload).toMatchObject({
      action: 'turn.execute',
      assistantProfile: 'authenticated_customer',
      authorizationContextDigest: 'd'.repeat(64),
      activationId: '00000000-0000-4000-8000-000000000010',
      graphRevision: 'graph-r1',
      knowledgeRevision: 'knowledge-r1',
      manifestSha256: 'c'.repeat(64),
      policyRevision: 'policy-r1',
      requestHash: 'a'.repeat(64),
    });
    expect(payload.exp! - payload.iat!).toBe(30);
  });

  it('rotates signing to an overlapping EdDSA key by active kid', async () => {
    const config = trustConfig('api-ai-next');
    const keyring = new InternalAiAssertionKeyring(config);
    const signed = await new InternalAiAssertionSigner(config, keyring).sign(
      validInput(),
    );

    expect(decodeProtectedHeader(signed.token)).toMatchObject({
      alg: 'EdDSA',
      kid: 'api-ai-next',
    });
    const jwks = keyring.publicJwks();
    expect(jwks.keys).toHaveLength(2);
    const next = jwks.keys.find(({ kid }) => kid === 'api-ai-next');
    expect(next).toBeDefined();
    const verificationKey = await importJWK(
      { ...next!, key_ops: [...next!.key_ops] },
      'EdDSA',
    );
    await expect(
      jwtVerify(signed.token, verificationKey, {
        algorithms: ['EdDSA'],
        audience: 'vfbiz-ai',
        issuer: 'vfbiz-api',
      }),
    ).resolves.toBeDefined();
  });

  it('fails closed when configured algorithm does not match key type', () => {
    expect(
      () =>
        new InternalAiAssertionKeyring(
          trustConfig('api-ai-current', [
            {
              alg: 'EdDSA',
              kid: 'api-ai-current',
              privateKeyFile: es256KeyFile,
            },
          ]),
        ),
    ).toThrow('must be an Ed25519 private key');
  });

  it('rejects a missing active key before module startup completes', () => {
    expect(() => trustConfig('api-ai-missing')).toThrow(
      'active key id is absent from the keyring',
    );
  });

  it('rejects inline or relative key material references', () => {
    expect(() =>
      trustConfig('api-ai-current', [
        {
          alg: 'ES256',
          kid: 'api-ai-current',
          privateKeyFile:
            '-----BEGIN PRIVATE KEY-----not-a-file-----END PRIVATE KEY-----',
        },
      ]),
    ).toThrow('absolute privateKeyFile');
  });

  it('rejects a private key readable by group or other users', () => {
    const insecureKeyFile = join(directory, 'insecure.pem');
    writePrivateKey(
      insecureKeyFile,
      generateKeyPairSync('ec', { namedCurve: 'P-256' }).privateKey,
    );
    chmodSync(insecureKeyFile, 0o644);
    expect(
      () =>
        new InternalAiAssertionKeyring(
          trustConfig('api-ai-current', [
            {
              alg: 'ES256',
              kid: 'api-ai-current',
              privateKeyFile: insecureKeyFile,
            },
          ]),
        ),
    ).toThrow('readable only by its owner');
  });

  it('rejects an invalid budget before signing', async () => {
    const config = trustConfig('api-ai-current');
    const signer = new InternalAiAssertionSigner(
      config,
      new InternalAiAssertionKeyring(config),
    );
    await expect(
      signer.sign({
        ...validInput(),
        budget: { ...validInput().budget, maxModelTokens: 0 },
      }),
    ).rejects.toThrow('budget is invalid');
  });

  it('rejects an invalid authorization context binding before signing', async () => {
    const config = trustConfig('api-ai-current');
    const signer = new InternalAiAssertionSigner(
      config,
      new InternalAiAssertionKeyring(config),
    );
    await expect(
      signer.sign({
        ...validInput(),
        authorizationContextDigest: 'not-a-digest',
      }),
    ).rejects.toThrow('authorization context digest is invalid');
  });

  it('keeps the module startup-safe but signing fail-closed when disabled', async () => {
    const service = new ConfigService<EnvironmentVariables, true>({
      VFBIZ_INTERNAL_AI_ENABLED: false,
      VFBIZ_INTERNAL_AI_REQUEST_TIMEOUT_MS: 15_000,
      VFBIZ_INTERNAL_AI_RETRY_BUDGET: 1,
      VFBIZ_INTERNAL_AI_ASSERTION_ISSUER: 'vfbiz-api',
      VFBIZ_INTERNAL_AI_ASSERTION_AUDIENCE: 'vfbiz-ai',
      VFBIZ_INTERNAL_AI_ASSERTION_TTL_SECONDS: 30,
    });
    const config = new InternalAiTrustConfig(service);
    const keyring = new InternalAiAssertionKeyring(config);

    expect(config).toMatchObject({ baseUrl: null, enabled: false });
    expect(keyring.publicJwks()).toEqual({ keys: [] });
    await expect(
      new InternalAiAssertionSigner(config, keyring).sign(validInput()),
    ).rejects.toThrow('signing is disabled');
  });

  function trustConfig(
    activeKeyId: string,
    keys: readonly {
      readonly alg: 'ES256' | 'EdDSA';
      readonly kid: string;
      readonly privateKeyFile: string;
    }[] = [
      {
        alg: 'ES256',
        kid: 'api-ai-current',
        privateKeyFile: es256KeyFile,
      },
      {
        alg: 'EdDSA',
        kid: 'api-ai-next',
        privateKeyFile: edDsaKeyFile,
      },
    ],
  ): InternalAiTrustConfig {
    const values = {
      VFBIZ_INTERNAL_AI_ENABLED: true,
      VFBIZ_INTERNAL_AI_BASE_URL: 'http://127.0.0.1:8888',
      VFBIZ_INTERNAL_AI_ALLOWED_HOSTS: '127.0.0.1',
      VFBIZ_INTERNAL_AI_REQUEST_TIMEOUT_MS: 15_000,
      VFBIZ_INTERNAL_AI_RETRY_BUDGET: 1,
      VFBIZ_INTERNAL_AI_ASSERTION_ISSUER: 'vfbiz-api',
      VFBIZ_INTERNAL_AI_ASSERTION_AUDIENCE: 'vfbiz-ai',
      VFBIZ_INTERNAL_AI_ASSERTION_TTL_SECONDS: 30,
      VFBIZ_INTERNAL_AI_ASSERTION_ACTIVE_KEY_ID: activeKeyId,
      VFBIZ_INTERNAL_AI_ASSERTION_KEYRING: JSON.stringify({ keys }),
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
    } as unknown as EnvironmentVariables;
    const configService = new ConfigService<EnvironmentVariables, true>(values);
    return new InternalAiTrustConfig(configService);
  }
});

function validInput(): InternalAiExecutionAssertionInput {
  return {
    action: 'turn.execute',
    activationId: '00000000-0000-4000-8000-000000000010',
    assistantProfile: 'authenticated_customer',
    authorizationContextDigest: 'd'.repeat(64),
    authorization: {
      allowedTools: ['search_public_knowledge', 'get_customer_garage'],
      kind: 'authenticated_customer',
      scopes: ['customer.chat', 'garage.read'],
      subjectRef: 'b'.repeat(64),
    },
    budget: {
      deadlineAt: new Date(Date.now() + 60_000).toISOString(),
      maxCostMicros: 100_000,
      maxModelTokens: 2_000,
    },
    conversationVersion: 7,
    correlationId: randomUUID(),
    fencingToken: 11,
    locale: 'vi',
    graphRevision: 'graph-r1',
    knowledgeRevision: 'knowledge-r1',
    manifestSha256: 'c'.repeat(64),
    policyRevision: 'policy-r1',
    requestHash: 'a'.repeat(64),
    requestId: randomUUID(),
    sessionId: randomUUID(),
    turnId: randomUUID(),
  };
}

function writePrivateKey(path: string, key: KeyObject): void {
  writeFileSync(path, key.export({ format: 'pem', type: 'pkcs8' }), {
    mode: 0o600,
  });
  chmodSync(path, 0o600);
}
