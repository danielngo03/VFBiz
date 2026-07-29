import { createServer, type IncomingMessage, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import type { InternalAiTrustConfig } from '../../../src/platform/config/internal-ai-trust.config';
import type { InternalAiAssertionSigner } from '../../../src/platform/security/internal-ai-assertion-signer';
import type { InternalAiExecutionAssertionInput } from '../../../src/platform/security/internal-ai-execution-assertion';
import type { ConversationAiExecutionRequest } from '../../../src/modules/engagement/application/runtime/conversation-ai.transport';
import {
  ConversationAiTransportError,
  InternalAiConversationTransport,
} from '../../../src/modules/engagement/infrastructure/ai/internal-ai-conversation.transport';

const sessionId = '123e4567-e89b-42d3-a456-426614174000';
const turnId = '223e4567-e89b-42d3-a456-426614174000';
const requestId = '323e4567-e89b-42d3-a456-426614174000';
const correlationId = '423e4567-e89b-42d3-a456-426614174000';

describe('Internal AI conversation transport integration', () => {
  let baseUrl: string;
  let server: Server;
  let requests: {
    assertion: string | undefined;
    body: string;
    path: string;
  }[];
  let retryAttempts: number;

  beforeAll(async () => {
    requests = [];
    retryAttempts = 0;
    server = createServer((request, response) => {
      void readBody(request)
        .then((body) => {
          requests.push({
            assertion: header(request, 'x-vfbiz-ai-assertion'),
            body,
            path: request.url ?? '',
          });
          const parsed = JSON.parse(body) as { message?: string };
          if (parsed.message === 'retry' && retryAttempts++ === 0) {
            response
              .writeHead(503, {
                'content-type': 'application/problem+json',
              })
              .end(
                JSON.stringify({
                  code: 'PROVIDER_UNAVAILABLE',
                  correlationId,
                  retryable: true,
                  status: 503,
                  title: 'Unavailable',
                  type: 'urn:vfbiz:problem:provider-unavailable',
                }),
              );
            return;
          }
          if (parsed.message === 'delay') {
            setTimeout(() => {
              if (!response.destroyed) {
                response
                  .writeHead(200, { 'content-type': 'application/json' })
                  .end(JSON.stringify(conversationalResult()));
              }
            }, 500);
            return;
          }
          if (request.url?.endsWith('/cancel') === true) {
            response.writeHead(202).end();
            return;
          }
          response
            .writeHead(200, { 'content-type': 'application/json' })
            .end(JSON.stringify(conversationalResult()));
        })
        .catch(() => response.writeHead(500).end());
    });
    await new Promise<void>((resolve) =>
      server.listen(0, '127.0.0.1', resolve),
    );
    const address = server.address() as AddressInfo;
    baseUrl = `http://127.0.0.1:${address.port}`;
  });

  afterAll(async () => {
    await new Promise<void>((resolve, reject) =>
      server.close((error) =>
        error === undefined ? resolve() : reject(error),
      ),
    );
  });

  beforeEach(() => {
    requests.length = 0;
    retryAttempts = 0;
  });

  it('uses the real HTTP boundary and a new assertion for each retry', async () => {
    const signer = fakeSigner();
    const transport = createTransport(signer, { retryBudget: 1 });

    await expect(
      transport.execute({ ...executionRequest(), content: 'retry' }),
    ).resolves.toMatchObject({ outcome: 'conversational' });

    expect(requests).toHaveLength(2);
    expect(requests.every(({ assertion }) => assertion !== undefined)).toBe(
      true,
    );
    expect(signer.sign).toHaveBeenCalledTimes(2);
    expect(signer.sign.mock.calls[0]?.[0].requestHash).toBe(
      signer.sign.mock.calls[1]?.[0].requestHash,
    );
  });

  it('aborts an in-flight HTTP request without accepting a late result', async () => {
    const transport = createTransport(fakeSigner(), {
      requestTimeoutMs: 5_000,
      retryBudget: 0,
    });
    const controller = new AbortController();
    const pending = transport.execute(
      { ...executionRequest(), content: 'delay' },
      controller.signal,
    );
    setTimeout(() => controller.abort(new Error('customer-cancelled')), 25);

    await expect(pending).rejects.toMatchObject({
      code: 'cancelled',
      retryable: false,
    } satisfies Partial<ConversationAiTransportError>);
  });

  it('sends cancellation to the durable turn-specific endpoint', async () => {
    const transport = createTransport(fakeSigner());

    await transport.cancel({
      accessScope: executionRequest().accessScope,
      assistantProfile: 'public_customer',
      authorizationContextDigest: executionRequest().authorizationContextDigest,
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
    });

    expect(requests[0]?.path).toBe(
      `/internal/v1/conversation/turns/${turnId}/cancel`,
    );
    expect(JSON.parse(requests[0].body)).toEqual({
      conversationVersion: 2,
      fencingToken: 7,
      reason: 'user_interrupt',
      requestId,
    });
  });

  function createTransport(
    signer: ReturnType<typeof fakeSigner>,
    overrides: Partial<InternalAiTrustConfig> = {},
  ): InternalAiConversationTransport {
    return new InternalAiConversationTransport(
      {
        activeKeyId: 'key-1',
        allowedHosts: new Set(['127.0.0.1']),
        assertionAudience: 'vfbiz-ai',
        assertionIssuer: 'vfbiz-api',
        assertionTtlSeconds: 30,
        baseUrl,
        dispatchEnabled: true,
        enabled: true,
        graphRevision: 'graph-r1',
        keyReferences: [],
        knowledgeRevision: 'knowledge-r1',
        policyRevision: 'policy-r1',
        requestTimeoutMs: 2_000,
        retryBudget: 0,
        subjectPseudonymizationKey:
          'MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=',
        ...overrides,
      } as unknown as InternalAiTrustConfig,
      signer as unknown as InternalAiAssertionSigner,
    );
  }
});

function executionRequest(): ConversationAiExecutionRequest {
  return {
    accessScope: {
      capabilityHash: 'a'.repeat(64),
      kind: 'public_capability',
      profile: 'public_customer',
    },
    assistantProfile: 'public_customer',
    authorizationContextDigest: 'e'.repeat(64),
    budget: { maxCostMicros: 10_000, maxModelTokens: 1_000 },
    confirmedEntities: [],
    content: 'hello',
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
    taskContext: null,
    turnId,
  };
}

function fakeSigner() {
  let sequence = 0;
  return {
    sign: jest.fn(
      (
        input: InternalAiExecutionAssertionInput,
      ): Promise<{
        expiresAt: number;
        jti: string;
        kid: string;
        token: string;
      }> => {
        void input;
        sequence += 1;
        return Promise.resolve({
          expiresAt: Math.floor(Date.now() / 1_000) + 30,
          jti: `523e4567-e89b-42d3-a456-${String(sequence).padStart(12, '0')}`,
          kid: 'key-1',
          token: `header.payload.signature-${sequence}`,
        });
      },
    ),
  };
}

function conversationalResult() {
  const issuedAt = new Date();
  return {
    citations: [],
    message: 'Xin chào.',
    outcome: 'conversational',
    releaseRevision: '00000000-0000-4000-8000-000000000010',
    releaseCommitReceipt: {
      activationEnvelopeSha256: 'b'.repeat(64),
      activationId: '00000000-0000-4000-8000-000000000010',
      candidateSha256: 'a'.repeat(64),
      conversationVersion: 2,
      expiresAt: new Date(issuedAt.getTime() + 15_000).toISOString(),
      fencingToken: 7,
      issuedAt: issuedAt.toISOString(),
      leaseId: '00000000-0000-4000-8000-000000000001',
      pointerRevision: 1,
      requestId,
      sessionId,
      turnId,
    },
    revisions: {
      graph: 'graph-r1',
      knowledge: 'knowledge-r1',
      policy: 'policy-r1',
    },
    usage: { costMicros: 10, modelTokens: 5 },
  };
}

async function readBody(request: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    request.on('data', (chunk: Buffer | string) => {
      chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
    });
    request.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    request.on('error', reject);
  });
}

function header(request: IncomingMessage, name: string): string | undefined {
  const value = request.headers[name];
  return Array.isArray(value) ? value[0] : value;
}
