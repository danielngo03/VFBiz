import { createHash, createHmac } from 'node:crypto';
import { Injectable } from '@nestjs/common';
import { InternalAiTrustConfig } from '../../../../platform/config/internal-ai-trust.config';
import { InternalAiAssertionSigner } from '../../../../platform/security/internal-ai-assertion-signer';
import type {
  InternalAiAuthorization,
  InternalAiReadOnlyTool,
} from '../../../../platform/security/internal-ai-execution-assertion';
import {
  ConversationAiTransport,
  ConversationAiTransportError,
  type ConversationAiCancellationRequest,
  type ConversationAiCancellationResult,
  type ConversationAiExecutionRequest,
  type ConversationAiExecutionResult,
} from '../../application/runtime/conversation-ai.transport';
import { InternalAiResponseVerifier } from './internal-ai-response-verifier';
export {
  ConversationAiTransportError,
  type ConversationAiTransportFailureCode,
} from '../../application/runtime/conversation-ai.transport';

const EXECUTION_PATH = '/internal/v1/conversation/turns';
const CIRCUIT_FAILURE_THRESHOLD = 5;
const CIRCUIT_OPEN_MILLISECONDS = 30_000;
const MAX_RESPONSE_BYTES = 128 * 1_024;
const SHA_256_PATTERN = /^[a-f0-9]{64}$/;
const REVISION_PATTERN = /^[\x21-\x7e]{1,160}$/;
// Business tools remain unavailable until the API-side tool authorization and
// execution gateway is delivered. Authentication alone must never broaden the
// model's authority.
const AUTHENTICATED_TOOLS: readonly InternalAiReadOnlyTool[] = Object.freeze([
  'search_public_knowledge',
]);

@Injectable()
export class InternalAiConversationTransport extends ConversationAiTransport {
  private circuitOpenedUntil = 0;
  private consecutiveFailures = 0;
  private readonly responseVerifier: InternalAiResponseVerifier;

  constructor(
    private readonly config: InternalAiTrustConfig,
    private readonly signer: InternalAiAssertionSigner,
  ) {
    super();
    this.responseVerifier = new InternalAiResponseVerifier(
      this.config.responseVerificationKeyReferences ?? [],
    );
  }

  async execute(
    request: ConversationAiExecutionRequest,
    signal?: AbortSignal,
  ): Promise<ConversationAiExecutionResult> {
    const body = {
      confirmedEntities: request.confirmedEntities.map((entity) => ({
        authority: entity.authority,
        authorityDigest: entity.provenanceDigest,
        classification: entity.classification,
        confirmedAt: entity.confirmedAt.toISOString(),
        expiresAt: entity.expiresAt.toISOString(),
        kind: entity.kind,
        reference: entity.opaqueReference,
        sourceRevision: entity.sourceRevision,
      })),
      conversationVersion: request.conversationVersion,
      correlationId: request.correlationId,
      fencingToken: request.fencingToken,
      locale: request.locale,
      message: request.content,
      requestId: request.requestId,
      sessionId: request.sessionId,
      turnId: request.turnId,
    };
    const authorization = authorizationFor(
      request,
      this.config.subjectPseudonymizationKey,
    );
    const response = await this.send({
      action: 'turn.execute',
      authorization,
      body,
      budget: request.budget,
      correlationId: request.correlationId,
      deadlineAt: request.deadlineAt,
      method: 'POST',
      path: EXECUTION_PATH,
      policyRevision: request.policyRevision,
      request,
      signal,
    });
    try {
      const document = await readJsonDocument(response);
      this.verifyResponse(
        document,
        response,
        request.requestId,
        request.correlationId,
      );
      const result = parseExecutionResult(
        document.value,
        {
          graph: request.release.graphRevision,
          knowledge: request.release.knowledgeRevision,
          policy: request.release.policyRevision,
        },
        request,
      );
      if (
        result.outcome === 'tool_proposal' &&
        !new Set<InternalAiReadOnlyTool>(authorization.allowedTools).has(
          result.tool,
        )
      ) {
        throw new ConversationAiTransportError('policy_denied', false);
      }
      this.recordSuccess();
      return result;
    } catch (error) {
      const failure = normalizeTransportFailure(error, signal);
      this.recordFailure(failure);
      throw failure;
    }
  }

  async cancel(
    request: ConversationAiCancellationRequest,
    signal?: AbortSignal,
  ): Promise<ConversationAiCancellationResult> {
    const path = `${EXECUTION_PATH}/${encodeURIComponent(request.turnId)}/cancel`;
    const body = {
      conversationVersion: request.conversationVersion,
      fencingToken: request.fencingToken,
      reason: request.reason,
      requestId: request.requestId,
    };
    try {
      const response = await this.send({
        action: 'turn.cancel',
        authorization: authorizationFor(
          request,
          this.config.subjectPseudonymizationKey,
        ),
        body,
        budget: request.budget,
        correlationId: request.correlationId,
        deadlineAt: new Date(Date.now() + this.config.requestTimeoutMs),
        method: 'POST',
        path,
        policyRevision: request.policyRevision,
        request,
        signal,
      });
      const document = await readJsonDocument(response);
      this.verifyResponse(
        document,
        response,
        request.requestId,
        request.correlationId,
      );
      this.recordSuccess();
      return { status: 'accepted' };
    } catch (error) {
      const failure = normalizeTransportFailure(error, signal);
      this.recordFailure(failure);
      throw failure;
    }
  }

  private verifyResponse(
    document: Readonly<{ bytes: Uint8Array; value: unknown }>,
    response: Response,
    requestId: string,
    correlationId: string,
  ): void {
    if (!this.responseVerifier.enabled) return;
    this.responseVerifier.verify({
      body: document.bytes,
      correlationId,
      headers: response.headers,
      requestId,
    });
  }

  private async send(input: {
    action: 'turn.cancel' | 'turn.execute';
    authorization: InternalAiAuthorization;
    body: Readonly<Record<string, unknown>>;
    budget: {
      readonly maxCostMicros: number;
      readonly maxModelTokens: number;
    };
    correlationId: string;
    deadlineAt: Date;
    method: 'POST';
    path: string;
    policyRevision: string;
    request: {
      readonly assistantProfile: 'authenticated_customer' | 'public_customer';
      readonly conversationVersion: number;
      readonly fencingToken: number;
      readonly locale: 'en' | 'vi';
      readonly release: ConversationAiExecutionRequest['release'];
      readonly requestId: string;
      readonly sessionId: string;
      readonly turnId: string;
    };
    signal?: AbortSignal;
  }): Promise<Response> {
    if (!this.config.enabled || this.config.baseUrl === null) {
      throw new ConversationAiTransportError('provider_unavailable', true);
    }
    if (input.signal?.aborted === true) {
      throw new ConversationAiTransportError('cancelled', false);
    }
    if (Date.now() < this.circuitOpenedUntil) {
      throw new ConversationAiTransportError('circuit_open', true);
    }
    if (input.policyRevision !== input.request.release.policyRevision) {
      throw new ConversationAiTransportError('policy_denied', false);
    }

    const canonicalBody = canonicalJson(input.body);
    const requestHash = canonicalRequestHash(
      input.method,
      input.path,
      canonicalBody,
    );
    const maximumAttempts = this.config.retryBudget + 1;
    let lastFailure: ConversationAiTransportError | null = null;

    for (let attempt = 1; attempt <= maximumAttempts; attempt += 1) {
      try {
        if (input.deadlineAt.getTime() <= Date.now()) {
          throw new ConversationAiTransportError('timeout', false);
        }
        const assertion = await this.signer.sign({
          action: input.action,
          assistantProfile: input.request.assistantProfile,
          authorization: input.authorization,
          budget: {
            deadlineAt: input.deadlineAt.toISOString(),
            maxCostMicros: input.budget.maxCostMicros,
            maxModelTokens: input.budget.maxModelTokens,
          },
          conversationVersion: input.request.conversationVersion,
          correlationId: input.correlationId,
          fencingToken: input.request.fencingToken,
          locale: input.request.locale,
          activationId: input.request.release.activationId,
          graphRevision: input.request.release.graphRevision,
          knowledgeRevision: input.request.release.knowledgeRevision,
          manifestSha256: input.request.release.manifestSha256,
          policyRevision: input.request.release.policyRevision,
          requestHash,
          requestId: input.request.requestId,
          sessionId: input.request.sessionId,
          turnId: input.request.turnId,
        });
        const remainingMilliseconds = input.deadlineAt.getTime() - Date.now();
        if (remainingMilliseconds <= 0) {
          throw new ConversationAiTransportError('timeout', false);
        }
        const response = await this.fetchWithTimeout(
          new URL(input.path, this.config.baseUrl),
          canonicalBody,
          assertion.token,
          input.correlationId,
          Math.min(this.config.requestTimeoutMs, remainingMilliseconds),
          input.signal,
        );
        if (input.deadlineAt.getTime() <= Date.now()) {
          await response.body?.cancel();
          throw new ConversationAiTransportError('timeout', false);
        }
        if (response.ok) {
          return response;
        }
        const failure = await mapFailure(response);
        throw failure;
      } catch (error) {
        const failure = normalizeTransportFailure(error, input.signal);
        if (!failure.retryable || attempt === maximumAttempts) {
          throw failure;
        }
        lastFailure = failure;
        await waitForRetry(attempt, input.signal);
      }
    }

    const failure =
      lastFailure ??
      new ConversationAiTransportError('provider_unavailable', true);
    throw failure;
  }

  private async fetchWithTimeout(
    url: URL,
    body: string,
    assertion: string,
    correlationId: string,
    timeoutMilliseconds: number,
    upstreamSignal?: AbortSignal,
  ): Promise<Response> {
    const controller = new AbortController();
    const timeout = setTimeout(
      () => controller.abort(new Error('internal-ai-timeout')),
      timeoutMilliseconds,
    );
    const abortUpstream = () =>
      controller.abort(upstreamSignal?.reason ?? new Error('cancelled'));
    upstreamSignal?.addEventListener('abort', abortUpstream, { once: true });
    try {
      return await fetch(url, {
        body,
        headers: {
          'content-type': 'application/json',
          'x-correlation-id': correlationId,
          'x-vfbiz-ai-assertion': assertion,
        },
        method: 'POST',
        redirect: 'error',
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeout);
      upstreamSignal?.removeEventListener('abort', abortUpstream);
    }
  }

  private recordFailure(error: ConversationAiTransportError): void {
    if (!error.retryable && error.code !== 'invalid_response') return;
    this.consecutiveFailures += 1;
    if (this.consecutiveFailures >= CIRCUIT_FAILURE_THRESHOLD) {
      this.circuitOpenedUntil = Date.now() + CIRCUIT_OPEN_MILLISECONDS;
      this.consecutiveFailures = 0;
    }
  }

  private recordSuccess(): void {
    this.consecutiveFailures = 0;
    this.circuitOpenedUntil = 0;
  }
}

function authorizationFor(
  input: {
    readonly accessScope:
      | {
          readonly capabilityHash: string;
          readonly kind: 'public_capability';
        }
      | {
          readonly issuer: string;
          readonly kind: 'authenticated_customer';
          readonly subject: string;
        };
  },
  pseudonymizationKey: string | null,
): InternalAiAuthorization {
  if (input.accessScope.kind === 'public_capability') {
    return {
      allowedTools: ['search_public_knowledge'],
      capabilityHash: input.accessScope.capabilityHash,
      kind: 'public_capability',
    };
  }
  if (pseudonymizationKey === null) {
    throw new ConversationAiTransportError('policy_denied', false);
  }
  return {
    allowedTools: AUTHENTICATED_TOOLS,
    kind: 'authenticated_customer',
    scopes: [],
    subjectRef: createHmac('sha256', Buffer.from(pseudonymizationKey, 'base64'))
      .update(
        `${input.accessScope.issuer}\u0000${input.accessScope.subject}`,
        'utf8',
      )
      .digest('hex'),
  };
}

function canonicalRequestHash(
  method: string,
  path: string,
  canonicalBody: string,
): string {
  return createHash('sha256')
    .update(`${method.toUpperCase()}\n${path}\n${canonicalBody}`, 'utf8')
    .digest('hex');
}

export function canonicalJson(value: unknown): string {
  if (
    value === null ||
    typeof value === 'boolean' ||
    typeof value === 'string'
  ) {
    return JSON.stringify(value);
  }
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) {
      throw new ConversationAiTransportError('invalid_response', false);
    }
    return String(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(',')}]`;
  }
  if (isRecord(value)) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(',')}}`;
  }
  throw new ConversationAiTransportError('invalid_response', false);
}

async function mapFailure(
  response: Response,
): Promise<ConversationAiTransportError> {
  const body = await readJson(response).catch(() => null);
  const code =
    isRecord(body) && typeof body.code === 'string' ? body.code : null;
  if (code === 'STALE_FENCING_TOKEN' || code === 'VERSION_CONFLICT') {
    return new ConversationAiTransportError('stale_execution', false);
  }
  if (code === 'POLICY_DENIED' || response.status === 403) {
    return new ConversationAiTransportError('policy_denied', false);
  }
  const retryable =
    (isRecord(body) && body.retryable === true) ||
    response.status === 429 ||
    response.status === 502 ||
    response.status === 503 ||
    response.status === 504;
  return new ConversationAiTransportError(
    retryable ? 'provider_unavailable' : 'invalid_response',
    retryable,
  );
}

function normalizeTransportFailure(
  error: unknown,
  upstreamSignal?: AbortSignal,
): ConversationAiTransportError {
  if (error instanceof ConversationAiTransportError) return error;
  if (upstreamSignal?.aborted === true) {
    return new ConversationAiTransportError('cancelled', false);
  }
  if (error instanceof DOMException && error.name === 'AbortError') {
    return new ConversationAiTransportError('timeout', true);
  }
  if (
    error instanceof Error &&
    (error.message === 'internal-ai-timeout' ||
      (error.cause instanceof Error &&
        error.cause.message === 'internal-ai-timeout'))
  ) {
    return new ConversationAiTransportError('timeout', true);
  }
  return new ConversationAiTransportError('provider_unavailable', true);
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await readJsonUnchecked(response);
  } catch (error) {
    if (error instanceof ConversationAiTransportError) throw error;
    throw new ConversationAiTransportError('invalid_response', false);
  }
}

async function readJsonDocument(
  response: Response,
): Promise<Readonly<{ bytes: Uint8Array; value: unknown }>> {
  try {
    return await readJsonDocumentUnchecked(response);
  } catch (error) {
    if (error instanceof ConversationAiTransportError) throw error;
    throw new ConversationAiTransportError('invalid_response', false);
  }
}

async function readJsonUnchecked(response: Response): Promise<unknown> {
  return (await readJsonDocumentUnchecked(response)).value;
}

async function readJsonDocumentUnchecked(
  response: Response,
): Promise<Readonly<{ bytes: Uint8Array; value: unknown }>> {
  const declaredLength = response.headers.get('content-length');
  if (
    declaredLength !== null &&
    Number.isFinite(Number(declaredLength)) &&
    Number(declaredLength) > MAX_RESPONSE_BYTES
  ) {
    throw new ConversationAiTransportError('invalid_response', false);
  }
  if (response.body === null) return { bytes: new Uint8Array(), value: null };
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_RESPONSE_BYTES) {
      await reader.cancel();
      throw new ConversationAiTransportError('invalid_response', false);
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  if (text.length === 0) return { bytes, value: null };
  try {
    return { bytes, value: JSON.parse(text) as unknown };
  } catch {
    throw new ConversationAiTransportError('invalid_response', false);
  }
}

async function waitForRetry(
  attempt: number,
  signal?: AbortSignal,
): Promise<void> {
  const delayMilliseconds = Math.min(25 * 2 ** (attempt - 1), 250);
  await new Promise<void>((resolve, reject) => {
    if (signal?.aborted === true) {
      reject(new ConversationAiTransportError('cancelled', false));
      return;
    }
    const timeout = setTimeout(() => {
      signal?.removeEventListener('abort', abort);
      resolve();
    }, delayMilliseconds);
    const abort = () => {
      clearTimeout(timeout);
      signal?.removeEventListener('abort', abort);
      reject(new ConversationAiTransportError('cancelled', false));
    };
    signal?.addEventListener('abort', abort, { once: true });
  });
}

function parseExecutionResult(
  value: unknown,
  expectedRevisions: {
    readonly graph: string;
    readonly knowledge: string;
    readonly policy: string;
  },
  expectedBinding: {
    readonly release: ConversationAiExecutionRequest['release'];
    readonly conversationVersion: number;
    readonly fencingToken: number;
    readonly requestId: string;
    readonly sessionId: string;
    readonly turnId: string;
  },
): ConversationAiExecutionResult {
  if (!isRecord(value) || !validUsage(value.usage)) {
    throw new ConversationAiTransportError('invalid_response', false);
  }
  const releaseRevision = requiredRevision(value.releaseRevision);
  if (releaseRevision !== expectedBinding.release.activationId) {
    throw new ConversationAiTransportError('stale_execution', false);
  }
  const releaseCommitReceipt =
    value.outcome === 'failed_safely'
      ? null
      : parseReleaseCommitReceipt(
          value.releaseCommitReceipt,
          releaseRevision,
          expectedBinding,
        );
  const revisions = parseAndVerifyRevisions(value.revisions, expectedRevisions);
  const usage = {
    costMicros: value.usage.costMicros,
    modelTokens: value.usage.modelTokens,
  };
  if (value.outcome === 'answered') {
    if (
      !hasExactKeys(value, [
        'citations',
        'message',
        'outcome',
        'releaseRevision',
        'releaseCommitReceipt',
        'revisions',
        'usage',
      ]) ||
      !requiredMessage(value.message) ||
      !Array.isArray(value.citations) ||
      value.citations.length < 1 ||
      value.citations.length > 20
    ) {
      throw new ConversationAiTransportError('invalid_response', false);
    }
    return {
      citations: value.citations.map((citation) =>
        parseCitation(citation, revisions.knowledge),
      ),
      message: value.message,
      outcome: 'answered',
      releaseRevision,
      releaseCommitReceipt,
      revisions,
      usage,
    };
  }
  if (value.outcome === 'conversational' || value.outcome === 'refused') {
    if (
      !hasExactKeys(value, [
        'citations',
        'message',
        'outcome',
        'releaseRevision',
        'releaseCommitReceipt',
        'revisions',
        'usage',
      ]) ||
      !requiredMessage(value.message) ||
      !Array.isArray(value.citations) ||
      value.citations.length !== 0
    ) {
      throw new ConversationAiTransportError('invalid_response', false);
    }
    return {
      message: value.message,
      outcome: value.outcome,
      releaseRevision,
      releaseCommitReceipt,
      revisions,
      usage,
    };
  }
  if (value.outcome === 'clarification_required') {
    if (
      !hasExactKeys(value, [
        'message',
        'outcome',
        'pendingSlots',
        'releaseRevision',
        'releaseCommitReceipt',
        'revisions',
        'usage',
      ]) ||
      !requiredMessage(value.message) ||
      !Array.isArray(value.pendingSlots) ||
      value.pendingSlots.length > 16 ||
      value.pendingSlots.some(
        (slot) =>
          typeof slot !== 'string' || slot.length < 1 || slot.length > 80,
      )
    ) {
      throw new ConversationAiTransportError('invalid_response', false);
    }
    return {
      message: value.message,
      outcome: 'clarification_required',
      pendingSlots: value.pendingSlots,
      releaseRevision,
      releaseCommitReceipt,
      revisions,
      usage,
    };
  }
  if (value.outcome === 'failed_safely') {
    if (
      !hasExactKeys(value, [
        'code',
        'message',
        'outcome',
        'releaseRevision',
        'revisions',
        'usage',
      ]) ||
      value.code !== 'RELEASE_SUPPRESSED' ||
      !requiredMessage(value.message)
    ) {
      throw new ConversationAiTransportError('invalid_response', false);
    }
    return {
      code: 'RELEASE_SUPPRESSED',
      message: value.message,
      outcome: 'failed_safely',
      releaseRevision,
      releaseCommitReceipt: null,
      revisions,
      usage,
    };
  }
  if (value.outcome === 'handoff_recommended') {
    if (
      !hasExactKeys(value, [
        'customerMessage',
        'outcome',
        'reason',
        'releaseRevision',
        'releaseCommitReceipt',
        'revisions',
        'usage',
      ]) ||
      !requiredMessage(value.customerMessage) ||
      !isHandoffReason(value.reason)
    ) {
      throw new ConversationAiTransportError('invalid_response', false);
    }
    return {
      customerMessage: value.customerMessage,
      outcome: 'handoff_recommended',
      reason: value.reason,
      releaseRevision,
      releaseCommitReceipt,
      revisions,
      usage,
    };
  }
  if (value.outcome === 'tool_proposal') {
    if (
      !hasExactKeys(value, [
        'arguments',
        'argumentsHash',
        'outcome',
        'releaseRevision',
        'releaseCommitReceipt',
        'revisions',
        'schemaVersion',
        'tool',
        'usage',
      ]) ||
      !isReadOnlyTool(value.tool) ||
      typeof value.schemaVersion !== 'string' ||
      value.schemaVersion.length < 1 ||
      value.schemaVersion.length > 80 ||
      !isRecord(value.arguments) ||
      Object.keys(value.arguments).length > 32 ||
      typeof value.argumentsHash !== 'string' ||
      !SHA_256_PATTERN.test(value.argumentsHash) ||
      value.argumentsHash !==
        createHash('sha256')
          .update(canonicalJson(value.arguments), 'utf8')
          .digest('hex')
    ) {
      throw new ConversationAiTransportError('invalid_response', false);
    }
    return {
      arguments: Object.freeze({ ...value.arguments }),
      argumentsHash: value.argumentsHash,
      outcome: 'tool_proposal',
      releaseRevision,
      releaseCommitReceipt,
      revisions,
      schemaVersion: value.schemaVersion,
      tool: value.tool,
      usage,
    };
  }
  throw new ConversationAiTransportError('invalid_response', false);
}

function parseReleaseCommitReceipt(
  value: unknown,
  releaseRevision: string,
  expected: {
    readonly release: ConversationAiExecutionRequest['release'];
    readonly conversationVersion: number;
    readonly fencingToken: number;
    readonly requestId: string;
    readonly sessionId: string;
    readonly turnId: string;
  },
): {
  readonly activationEnvelopeSha256: string;
  readonly activationId: string;
  readonly candidateSha256: string;
  readonly conversationVersion: number;
  readonly expiresAt: Date;
  readonly fencingToken: number;
  readonly issuedAt: Date;
  readonly leaseId: string;
  readonly pointerRevision: number;
  readonly requestId: string;
  readonly sessionId: string;
  readonly turnId: string;
} {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      'activationEnvelopeSha256',
      'activationId',
      'candidateSha256',
      'conversationVersion',
      'expiresAt',
      'fencingToken',
      'issuedAt',
      'leaseId',
      'pointerRevision',
      'requestId',
      'sessionId',
      'turnId',
    ]) ||
    value.activationId !== releaseRevision ||
    typeof value.candidateSha256 !== 'string' ||
    !SHA_256_PATTERN.test(value.candidateSha256) ||
    typeof value.activationEnvelopeSha256 !== 'string' ||
    !SHA_256_PATTERN.test(value.activationEnvelopeSha256) ||
    value.activationEnvelopeSha256 !==
      expected.release.activationEnvelopeSha256 ||
    !Number.isSafeInteger(value.pointerRevision) ||
    (value.pointerRevision as number) < 1 ||
    value.pointerRevision !== expected.release.pointerRevision ||
    value.conversationVersion !== expected.conversationVersion ||
    value.fencingToken !== expected.fencingToken ||
    value.requestId !== expected.requestId ||
    value.sessionId !== expected.sessionId ||
    value.turnId !== expected.turnId ||
    typeof value.issuedAt !== 'string' ||
    typeof value.leaseId !== 'string' ||
    !/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(
      value.leaseId,
    ) ||
    typeof value.expiresAt !== 'string'
  ) {
    throw new ConversationAiTransportError('invalid_response', false);
  }
  const issuedAt = new Date(value.issuedAt);
  const expiresAt = new Date(value.expiresAt);
  if (
    Number.isNaN(issuedAt.getTime()) ||
    Number.isNaN(expiresAt.getTime()) ||
    issuedAt.getTime() > Date.now() + 5_000 ||
    issuedAt.getTime() < Date.now() - 30_000 ||
    expiresAt.getTime() <= issuedAt.getTime() ||
    expiresAt.getTime() - issuedAt.getTime() > 30_000 ||
    expiresAt.getTime() <= Date.now()
  ) {
    throw new ConversationAiTransportError('stale_execution', false);
  }
  return {
    activationEnvelopeSha256: value.activationEnvelopeSha256,
    activationId: value.activationId,
    candidateSha256: value.candidateSha256,
    conversationVersion: value.conversationVersion,
    expiresAt,
    fencingToken: value.fencingToken,
    issuedAt,
    leaseId: value.leaseId,
    pointerRevision: value.pointerRevision,
    requestId: value.requestId,
    sessionId: value.sessionId,
    turnId: value.turnId,
  };
}

function parseCitation(
  value: unknown,
  expectedKnowledgeRevision: string,
): {
  readonly retrievedAt: Date;
  readonly revision: string;
  readonly sourceId: string;
  readonly title: string;
  readonly uri: string;
} {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      'knowledgeRevision',
      'retrievedAt',
      'revision',
      'sourceId',
      'title',
      ...(value.uri === undefined ? [] : ['uri']),
    ]) ||
    value.knowledgeRevision !== expectedKnowledgeRevision ||
    typeof value.sourceId !== 'string' ||
    value.sourceId.length < 1 ||
    value.sourceId.length > 160 ||
    typeof value.revision !== 'string' ||
    value.revision.length < 1 ||
    value.revision.length > 160 ||
    typeof value.title !== 'string' ||
    value.title.length < 1 ||
    value.title.length > 255 ||
    (value.uri !== undefined &&
      (typeof value.uri !== 'string' ||
        value.uri.length < 1 ||
        value.uri.length > 1_024)) ||
    typeof value.retrievedAt !== 'string'
  ) {
    throw new ConversationAiTransportError('invalid_response', false);
  }
  if (
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/.test(
      value.retrievedAt,
    )
  ) {
    throw new ConversationAiTransportError('invalid_response', false);
  }
  const retrievedAt = new Date(value.retrievedAt);
  if (Number.isNaN(retrievedAt.getTime())) {
    throw new ConversationAiTransportError('invalid_response', false);
  }
  const uri =
    typeof value.uri === 'string'
      ? validatedCitationUri(value.uri)
      : `urn:vfbiz:knowledge-source:${encodeURIComponent(value.sourceId)}`;
  return {
    retrievedAt,
    revision: value.revision,
    sourceId: value.sourceId,
    title: value.title,
    uri,
  };
}

function parseAndVerifyRevisions(
  value: unknown,
  expected: {
    readonly graph: string | null;
    readonly knowledge: string | null;
    readonly policy: string | null;
  },
): {
  readonly graph: string;
  readonly knowledge: string;
  readonly policy: string;
} {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ['graph', 'knowledge', 'policy']) ||
    expected.graph === null ||
    expected.knowledge === null ||
    expected.policy === null ||
    value.graph !== expected.graph ||
    value.knowledge !== expected.knowledge ||
    value.policy !== expected.policy
  ) {
    throw new ConversationAiTransportError('stale_execution', false);
  }
  return {
    graph: expected.graph,
    knowledge: expected.knowledge,
    policy: expected.policy,
  };
}

function validatedCitationUri(value: string): string {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new ConversationAiTransportError('invalid_response', false);
  }
  if (!['https:', 'http:', 'urn:'].includes(parsed.protocol)) {
    throw new ConversationAiTransportError('invalid_response', false);
  }
  return value;
}

function validUsage(value: unknown): value is {
  readonly costMicros: number;
  readonly modelTokens: number;
} {
  return (
    isRecord(value) &&
    Number.isSafeInteger(value.costMicros) &&
    Number(value.costMicros) >= 0 &&
    Number(value.costMicros) <= 10_000_000 &&
    Number.isSafeInteger(value.modelTokens) &&
    Number(value.modelTokens) >= 0 &&
    Number(value.modelTokens) <= 32_000
  );
}

function requiredRevision(value: unknown): string {
  if (typeof value !== 'string' || !REVISION_PATTERN.test(value)) {
    throw new ConversationAiTransportError('invalid_response', false);
  }
  return value;
}

function requiredMessage(value: unknown): value is string {
  return (
    typeof value === 'string' && value.length >= 1 && value.length <= 12_000
  );
}

function isHandoffReason(
  value: unknown,
): value is
  | 'insufficient_evidence'
  | 'policy_required'
  | 'safety_risk'
  | 'tool_unavailable' {
  return (
    value === 'insufficient_evidence' ||
    value === 'policy_required' ||
    value === 'safety_risk' ||
    value === 'tool_unavailable'
  );
}

function isReadOnlyTool(value: unknown): value is InternalAiReadOnlyTool {
  return (
    value === 'get_customer_garage' ||
    value === 'get_vehicle_profile' ||
    value === 'list_charging_stations' ||
    value === 'search_public_knowledge'
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const actual = Object.keys(value).sort();
  const sortedExpected = [...expected].sort();
  return (
    actual.length === sortedExpected.length &&
    actual.every((key, index) => key === sortedExpected[index])
  );
}
