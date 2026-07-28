import {
  createHash,
  generateKeyPairSync,
  sign as signBytes,
} from 'node:crypto';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { InternalAiTrustConfig } from '../../../../platform/config/internal-ai-trust.config';
import type { InternalAiAssertionSigner } from '../../../../platform/security/internal-ai-assertion-signer';
import type { InternalAiExecutionAssertionInput } from '../../../../platform/security/internal-ai-execution-assertion';
import type { ConversationAiExecutionRequest } from '../../application/runtime/conversation-ai.transport';
import {
  canonicalJson,
  ConversationAiTransportError,
  InternalAiConversationTransport,
} from './internal-ai-conversation.transport';

const sessionId = '123e4567-e89b-42d3-a456-426614174000';
const turnId = '223e4567-e89b-42d3-a456-426614174000';
const requestId = '323e4567-e89b-42d3-a456-426614174000';
const correlationId = '423e4567-e89b-42d3-a456-426614174000';
const responseRevisions = {
  graph: 'graph-r1',
  knowledge: 'knowledge-r1',
  policy: 'policy-r1',
} as const;

describe('InternalAiConversationTransport', () => {
  const responseKeys = generateKeyPairSync('ed25519');
  const responseKeyDirectory = mkdtempSync(
    join(tmpdir(), 'vfbiz-ai-transport-response-'),
  );
  const responsePublicKeyFile = join(responseKeyDirectory, 'public.pem');
  writeFileSync(
    responsePublicKeyFile,
    responseKeys.publicKey.export({ format: 'pem', type: 'spki' }),
    { mode: 0o600 },
  );

  afterAll(() => {
    rmSync(responseKeyDirectory, { force: true, recursive: true });
  });
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('matches the canonical request hashing vectors', () => {
    const canonical = canonicalJson({ b: 2, a: 'xin chào' });
    expect(canonical).toBe('{"a":"xin chào","b":2}');
    expect(
      createHash('sha256')
        .update(`POST\n/internal/v1/conversation/turns\n${canonical}`, 'utf8')
        .digest('hex'),
    ).toBe('31b97507b879bf0ce647803edfb9a3d64f83b9154e672fa777db9afdac172b5a');
  });

  it('signs and accepts a strictly grounded answer', async () => {
    const { signer, transport } = fixture();
    const fetchMock = jest.spyOn(global, 'fetch').mockResolvedValue(
      jsonResponse(200, {
        citations: [
          {
            knowledgeRevision: 'knowledge-r1',
            retrievedAt: '2026-07-25T08:00:00.000Z',
            revision: 'source-r1',
            sourceId: 'source-1',
            title: 'Approved policy',
            uri: 'https://example.test/policies/1',
          },
        ],
        message: 'Câu trả lời có nguồn.',
        outcome: 'answered',
        releaseRevision: '00000000-0000-4000-8000-000000000010',
        revisions: responseRevisions,
        usage: { costMicros: 120, modelTokens: 40 },
      }),
    );

    const confirmedAt = new Date('2026-07-25T07:00:00.000Z');
    const expiresAt = new Date('2026-07-26T07:00:00.000Z');
    const result = await transport.execute({
      ...executionRequest(),
      confirmedEntities: [
        {
          authority: 'vehicle-catalog',
          classification: 'non_sensitive',
          confirmedAt,
          expiresAt,
          kind: 'vehicle_model',
          opaqueReference: 'vf-8',
          provenanceDigest: 'c'.repeat(64),
          sourceRevision: 'd'.repeat(64),
        },
      ],
    });

    expect(result.outcome).toBe('answered');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(signer.sign).toHaveBeenCalledTimes(1);
    const assertionInput = signer.sign.mock.calls[0][0];
    expect(assertionInput).toMatchObject({
      action: 'turn.execute',
      assistantProfile: 'public_customer',
      conversationVersion: 2,
      fencingToken: 7,
      requestId,
      sessionId,
      turnId,
    });
    expect(assertionInput.requestHash).toMatch(/^[a-f0-9]{64}$/);
    const rawBody = fetchMock.mock.calls[0][1]?.body;
    if (typeof rawBody !== 'string') throw new Error('Expected string body');
    const body = rawBody;
    expect(body).toBe(canonicalJson(JSON.parse(body) as unknown));
    expect(JSON.parse(body)).toMatchObject({
      confirmedEntities: [
        {
          authority: 'vehicle-catalog',
          authorityDigest: 'c'.repeat(64),
          classification: 'non_sensitive',
          confirmedAt: confirmedAt.toISOString(),
          expiresAt: expiresAt.toISOString(),
          kind: 'vehicle_model',
          reference: 'vf-8',
          sourceRevision: 'd'.repeat(64),
        },
      ],
    });
  });

  it('verifies a detached workload signature before parsing the response', async () => {
    const { transport } = fixture({
      responseVerificationKeyReferences: [
        {
          algorithm: 'EdDSA',
          kid: 'ai-response-current',
          publicKeyFile: responsePublicKeyFile,
        },
      ],
    });
    const payload = {
      citations: [],
      message: 'Không đủ bằng chứng.',
      outcome: 'refused',
      releaseCommitReceipt: releaseReceipt(),
      releaseRevision: '00000000-0000-4000-8000-000000000010',
      revisions: responseRevisions,
      usage: { costMicros: 10, modelTokens: 5 },
    };
    jest.spyOn(global, 'fetch').mockResolvedValue(signedResponse(payload));

    await expect(transport.execute(executionRequest())).resolves.toMatchObject({
      outcome: 'refused',
    });
  });

  it('rejects a tampered body even when signature headers are present', async () => {
    const { transport } = fixture({
      responseVerificationKeyReferences: [
        {
          algorithm: 'EdDSA',
          kid: 'ai-response-current',
          publicKeyFile: responsePublicKeyFile,
        },
      ],
    });
    const response = signedResponse({
      citations: [],
      message: 'Original.',
      outcome: 'refused',
      releaseCommitReceipt: releaseReceipt(),
      releaseRevision: '00000000-0000-4000-8000-000000000010',
      revisions: responseRevisions,
      usage: { costMicros: 10, modelTokens: 5 },
    });
    const tampered = new Response(
      JSON.stringify({ outcome: 'answered', message: 'Tampered.' }),
      { headers: response.headers, status: 200 },
    );
    jest.spyOn(global, 'fetch').mockResolvedValue(tampered);

    await expect(transport.execute(executionRequest())).rejects.toMatchObject({
      code: 'invalid_response',
      retryable: false,
    });
  });

  function signedResponse(payload: unknown): Response {
    const body = JSON.stringify(payload);
    const issuedAt = new Date(Date.now() - 1_000).toISOString();
    const expiresAt = new Date(Date.now() + 29_000).toISOString();
    const bodySha256 = createHash('sha256').update(body).digest('hex');
    const canonical = Buffer.from(
      `VFBIZ-AI-RESPONSE-V1\nai-response-current\n${issuedAt}\n${expiresAt}\n${requestId}\n${correlationId}\n${bodySha256}`,
      'utf8',
    );
    return new Response(body, {
      headers: {
        'content-type': 'application/json',
        'x-vfbiz-ai-response-body-sha256': bodySha256,
        'x-vfbiz-ai-response-expires-at': expiresAt,
        'x-vfbiz-ai-response-issued-at': issuedAt,
        'x-vfbiz-ai-response-key-id': 'ai-response-current',
        'x-vfbiz-ai-response-signature': signBytes(
          null,
          canonical,
          responseKeys.privateKey,
        ).toString('base64url'),
      },
      status: 200,
    });
  }

  function releaseReceipt(): Record<string, unknown> {
    return {
      activationEnvelopeSha256: 'b'.repeat(64),
      activationId: '00000000-0000-4000-8000-000000000010',
      candidateSha256: 'a'.repeat(64),
      conversationVersion: 2,
      expiresAt: new Date(Date.now() + 15_000).toISOString(),
      fencingToken: 7,
      issuedAt: new Date().toISOString(),
      leaseId: '00000000-0000-4000-8000-000000000001',
      pointerRevision: 1,
      requestId,
      sessionId,
      turnId,
    };
  }

  it('creates a new one-time assertion for a retryable attempt', async () => {
    const { signer, transport } = fixture({ retryBudget: 1 });
    jest
      .spyOn(global, 'fetch')
      .mockResolvedValueOnce(
        jsonResponse(503, {
          code: 'PROVIDER_UNAVAILABLE',
          correlationId,
          retryable: true,
          status: 503,
          title: 'Unavailable',
          type: 'urn:vfbiz:problem:provider-unavailable',
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse(200, {
          citations: [],
          message: 'Xin chào.',
          outcome: 'conversational',
          releaseRevision: '00000000-0000-4000-8000-000000000010',
          revisions: responseRevisions,
          usage: { costMicros: 10, modelTokens: 5 },
        }),
      );

    await expect(transport.execute(executionRequest())).resolves.toMatchObject({
      outcome: 'conversational',
    });
    expect(signer.sign).toHaveBeenCalledTimes(2);
  });

  it('fails closed when a factual answer has no citation', async () => {
    const { transport } = fixture();
    jest.spyOn(global, 'fetch').mockResolvedValue(
      jsonResponse(200, {
        citations: [],
        message: 'Unsupported factual answer.',
        outcome: 'answered',
        releaseRevision: '00000000-0000-4000-8000-000000000010',
        revisions: responseRevisions,
        usage: { costMicros: 10, modelTokens: 5 },
      }),
    );

    await expect(transport.execute(executionRequest())).rejects.toMatchObject({
      code: 'invalid_response',
      retryable: false,
    } satisfies Partial<ConversationAiTransportError>);
  });

  it('accepts a terminal clarification as a typed outcome', async () => {
    const { transport } = fixture();
    jest.spyOn(global, 'fetch').mockResolvedValue(
      jsonResponse(200, {
        message: 'Vui lòng cho biết phiên bản xe.',
        outcome: 'clarification_required',
        pendingSlots: ['vehicle_variant'],
        releaseRevision: '00000000-0000-4000-8000-000000000010',
        revisions: responseRevisions,
        usage: { costMicros: 20, modelTokens: 8 },
      }),
    );

    await expect(transport.execute(executionRequest())).resolves.toMatchObject({
      outcome: 'clarification_required',
      pendingSlots: ['vehicle_variant'],
    });
  });

  it('accepts failed-safely usage while suppressing answer content', async () => {
    const { transport } = fixture();
    jest.spyOn(global, 'fetch').mockResolvedValue(
      jsonResponse(200, {
        code: 'RELEASE_SUPPRESSED',
        message: 'Câu trả lời đã được chặn an toàn.',
        outcome: 'failed_safely',
        releaseRevision: '00000000-0000-4000-8000-000000000010',
        revisions: responseRevisions,
        usage: { costMicros: 250, modelTokens: 75 },
      }),
    );

    await expect(transport.execute(executionRequest())).resolves.toMatchObject({
      outcome: 'failed_safely',
      usage: { costMicros: 250, modelTokens: 75 },
    });
  });

  it('rejects a future-issued release receipt even when its duration is bounded', async () => {
    const { transport } = fixture();
    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          citations: [],
          message: 'Future response.',
          outcome: 'conversational',
          releaseRevision: '00000000-0000-4000-8000-000000000010',
          releaseCommitReceipt: {
            activationEnvelopeSha256: 'b'.repeat(64),
            activationId: '00000000-0000-4000-8000-000000000010',
            candidateSha256: 'a'.repeat(64),
            conversationVersion: 2,
            expiresAt: '2099-01-01T00:00:15.000Z',
            fencingToken: 7,
            issuedAt: '2099-01-01T00:00:00.000Z',
            leaseId: '00000000-0000-4000-8000-000000000001',
            pointerRevision: 1,
            requestId,
            sessionId,
            turnId,
          },
          revisions: responseRevisions,
          usage: { costMicros: 10, modelTokens: 5 },
        }),
        { status: 200 },
      ),
    );

    await expect(transport.execute(executionRequest())).rejects.toMatchObject({
      code: 'stale_execution',
      retryable: false,
    });
  });

  it('does not follow redirects while carrying an internal assertion', async () => {
    const { transport } = fixture();
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      jsonResponse(200, {
        citations: [],
        message: 'Safe conversational response.',
        outcome: 'conversational',
        releaseRevision: '00000000-0000-4000-8000-000000000010',
        revisions: responseRevisions,
        usage: { costMicros: 10, modelTokens: 5 },
      }),
    );

    await transport.execute(executionRequest());
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.any(URL),
      expect.objectContaining({ redirect: 'error' }),
    );
  });

  it('rejects a response that arrives after the signed deadline', async () => {
    const { transport } = fixture({ requestTimeoutMs: 1_000 });
    jest.spyOn(global, 'fetch').mockImplementation(
      async () =>
        new Promise<Response>((resolve) => {
          setTimeout(
            () =>
              resolve(
                jsonResponse(200, {
                  citations: [],
                  message: 'Late response.',
                  outcome: 'conversational',
                  releaseRevision: '00000000-0000-4000-8000-000000000010',
                  revisions: responseRevisions,
                  usage: { costMicros: 10, modelTokens: 5 },
                }),
              ),
            20,
          );
        }),
    );

    await expect(
      transport.execute({
        ...executionRequest(),
        deadlineAt: new Date(Date.now() + 5),
      }),
    ).rejects.toMatchObject({ code: 'timeout' });
  });

  it('rejects a tool proposal outside the signed profile allowlist', async () => {
    const { transport } = fixture();
    jest.spyOn(global, 'fetch').mockResolvedValue(
      jsonResponse(200, {
        arguments: {},
        argumentsHash:
          '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a',
        outcome: 'tool_proposal',
        releaseRevision: '00000000-0000-4000-8000-000000000010',
        revisions: responseRevisions,
        schemaVersion: '1',
        tool: 'get_vehicle_profile',
        usage: { costMicros: 10, modelTokens: 5 },
      }),
    );

    await expect(transport.execute(executionRequest())).rejects.toMatchObject({
      code: 'policy_denied',
      retryable: false,
    } satisfies Partial<ConversationAiTransportError>);
  });

  it('bounds internal response memory before parsing', async () => {
    const { transport } = fixture();
    jest
      .spyOn(global, 'fetch')
      .mockResolvedValue(
        new Response('x'.repeat(128 * 1_024 + 1), { status: 200 }),
      );

    await expect(transport.execute(executionRequest())).rejects.toMatchObject({
      code: 'invalid_response',
      retryable: false,
    } satisfies Partial<ConversationAiTransportError>);
  });

  it('rejects a session pinned to a different policy revision', async () => {
    const { signer, transport } = fixture();

    await expect(
      transport.execute({
        ...executionRequest(),
        policyRevision: 'old-policy',
      }),
    ).rejects.toMatchObject({
      code: 'policy_denied',
      retryable: false,
    } satisfies Partial<ConversationAiTransportError>);
    expect(signer.sign).not.toHaveBeenCalled();
  });

  it('rejects a response produced from a different release snapshot', async () => {
    const { transport } = fixture();
    jest.spyOn(global, 'fetch').mockResolvedValue(
      jsonResponse(200, {
        citations: [],
        message: 'Stale response.',
        outcome: 'conversational',
        releaseRevision: 'release-r0',
        revisions: {
          ...responseRevisions,
          knowledge: 'knowledge-r0',
        },
        usage: { costMicros: 10, modelTokens: 5 },
      }),
    );

    await expect(transport.execute(executionRequest())).rejects.toMatchObject({
      code: 'stale_execution',
      retryable: false,
    } satisfies Partial<ConversationAiTransportError>);
  });

  it('propagates a signed cancellation to the turn-specific path', async () => {
    const { signer, transport } = fixture();
    const fetchMock = jest
      .spyOn(global, 'fetch')
      .mockResolvedValue(new Response(null, { status: 202 }));

    await expect(
      transport.cancel({
        accessScope: executionRequest().accessScope,
        assistantProfile: 'public_customer',
        budget: executionRequest().budget,
        conversationVersion: 2,
        correlationId,
        fencingToken: 7,
        locale: 'vi',
        release: executionRequest().release,
        policyRevision: 'policy-r1',
        reason: 'user_interrupt',
        requestId,
        sessionId,
        turnId,
      }),
    ).resolves.toEqual({ status: 'accepted' });

    const requestUrl = fetchMock.mock.calls[0][0];
    expect(requestUrl).toBeInstanceOf(URL);
    expect((requestUrl as URL).href).toBe(
      `http://127.0.0.1:8888/internal/v1/conversation/turns/${turnId}/cancel`,
    );
    expect(signer.sign.mock.calls[0][0]).toMatchObject({
      action: 'turn.cancel',
      turnId,
    });
  });

  it('does not sign or call the network while disabled', async () => {
    const { signer, transport } = fixture({ baseUrl: null, enabled: false });
    const fetchMock = jest.spyOn(global, 'fetch');

    await expect(transport.execute(executionRequest())).rejects.toMatchObject({
      code: 'provider_unavailable',
    });
    expect(signer.sign).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

function executionRequest(): ConversationAiExecutionRequest {
  return {
    accessScope: {
      capabilityHash: 'a'.repeat(64),
      kind: 'public_capability',
      profile: 'public_customer',
    },
    assistantProfile: 'public_customer',
    budget: { maxCostMicros: 10_000, maxModelTokens: 1_000 },
    confirmedEntities: [],
    content: 'Chính sách bảo hành là gì?',
    conversationVersion: 2,
    correlationId,
    deadlineAt: new Date(Date.now() + 30_000),
    fencingToken: 7,
    locale: 'vi',
    release: {
      activationEnvelopeSha256: 'b'.repeat(64),
      activationId: '00000000-0000-4000-8000-000000000010',
      effectiveAt: new Date('2026-07-25T00:00:00.000Z'),
      expiresAt: new Date('2026-07-26T00:00:00.000Z'),
      graphRevision: 'graph-r1',
      knowledgeRevision: 'knowledge-r1',
      manifestSha256: 'a'.repeat(64),
      pointerRevision: 1,
      policyRevision: 'policy-r1',
    },
    policyRevision: 'policy-r1',
    requestId,
    sessionId,
    turnId,
  };
}

function fixture(override: Partial<InternalAiTrustConfig> = {}): {
  signer: {
    sign: jest.Mock<
      Promise<{
        expiresAt: number;
        jti: string;
        kid: string;
        token: string;
      }>,
      [InternalAiExecutionAssertionInput]
    >;
  };
  transport: InternalAiConversationTransport;
} {
  const config = {
    activeKeyId: 'key-1',
    allowedHosts: new Set(['127.0.0.1']),
    assertionAudience: 'vfbiz-ai',
    assertionIssuer: 'vfbiz-api',
    assertionTtlSeconds: 30,
    baseUrl: 'http://127.0.0.1:8888',
    dispatchEnabled: true,
    enabled: true,
    graphRevision: 'graph-r1',
    keyReferences: [],
    knowledgeRevision: 'knowledge-r1',
    policyRevision: 'policy-r1',
    requestTimeoutMs: 5_000,
    retryBudget: 0,
    subjectPseudonymizationKey: 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=',
    ...override,
  } as unknown as InternalAiTrustConfig;
  const signer = {
    sign: jest.fn().mockResolvedValue({
      expiresAt: Math.floor(Date.now() / 1_000) + 30,
      jti: '523e4567-e89b-42d3-a456-426614174000',
      kid: 'key-1',
      token: 'header.payload.signature',
    }),
  };
  return {
    signer,
    transport: new InternalAiConversationTransport(
      config,
      signer as unknown as InternalAiAssertionSigner,
    ),
  };
}

function jsonResponse(status: number, body: unknown): Response {
  const enriched =
    status >= 200 &&
    status < 300 &&
    body !== null &&
    typeof body === 'object' &&
    !Array.isArray(body) &&
    'outcome' in body &&
    body.outcome !== 'failed_safely' &&
    !('releaseCommitReceipt' in body)
      ? {
          ...body,
          releaseCommitReceipt: {
            activationEnvelopeSha256: 'b'.repeat(64),
            activationId:
              'releaseRevision' in body &&
              typeof body.releaseRevision === 'string'
                ? body.releaseRevision
                : '00000000-0000-4000-8000-000000000010',
            candidateSha256: 'a'.repeat(64),
            conversationVersion: 2,
            expiresAt: new Date(Date.now() + 15_000).toISOString(),
            fencingToken: 7,
            issuedAt: new Date().toISOString(),
            leaseId: '00000000-0000-4000-8000-000000000001',
            pointerRevision: 1,
            requestId,
            sessionId,
            turnId,
          },
        }
      : body;
  return new Response(JSON.stringify(enriched), {
    headers: { 'content-type': 'application/json' },
    status,
  });
}
