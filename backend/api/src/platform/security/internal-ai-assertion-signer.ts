import { randomUUID } from 'node:crypto';
import { Injectable } from '@nestjs/common';
import { SignJWT } from 'jose';
import { InternalAiTrustConfig } from '../config/internal-ai-trust.config';
import { InternalAiAssertionKeyring } from './internal-ai-assertion-keyring';
import type {
  InternalAiAuthorization,
  InternalAiExecutionAssertionClaims,
  InternalAiExecutionAssertionInput,
  InternalAiReadOnlyTool,
} from './internal-ai-execution-assertion';

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA_256_PATTERN = /^[a-f0-9]{64}$/;
const REVISION_PATTERN = /^[\x21-\x7e]{1,160}$/;
const RFC3339_WITH_TIMEZONE_PATTERN =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/;
const MAX_SAFE_INTEGER = Number.MAX_SAFE_INTEGER;
const READ_ONLY_TOOLS = new Set<InternalAiReadOnlyTool>([
  'get_customer_garage',
  'get_vehicle_profile',
  'list_charging_stations',
  'search_public_knowledge',
]);

export interface SignedInternalAiAssertion {
  readonly expiresAt: number;
  readonly jti: string;
  readonly kid: string;
  readonly token: string;
}

@Injectable()
export class InternalAiAssertionSigner {
  constructor(
    private readonly config: InternalAiTrustConfig,
    private readonly keyring: InternalAiAssertionKeyring,
  ) {}

  async sign(
    input: InternalAiExecutionAssertionInput,
  ): Promise<SignedInternalAiAssertion> {
    if (!this.config.enabled) {
      throw new Error('Internal AI assertion signing is disabled');
    }
    assertValidInput(input);
    const signingKey = this.keyring.activeSigningKey();
    const issuedAt = Math.floor(Date.now() / 1_000);
    const expiresAt = issuedAt + this.config.assertionTtlSeconds;
    const jti = randomUUID();
    const claims: InternalAiExecutionAssertionClaims = {
      action: input.action,
      activationId: input.activationId,
      assistantProfile: input.assistantProfile,
      authorizationContextDigest: input.authorizationContextDigest,
      authorization: immutableAuthorization(input.authorization),
      aud: this.config.assertionAudience,
      budget: Object.freeze({ ...input.budget }),
      conversationVersion: input.conversationVersion,
      correlationId: input.correlationId,
      exp: expiresAt,
      fencingToken: input.fencingToken,
      graphRevision: input.graphRevision,
      iat: issuedAt,
      iss: this.config.assertionIssuer,
      jti,
      knowledgeRevision: input.knowledgeRevision,
      locale: input.locale,
      nbf: issuedAt,
      policyRevision: input.policyRevision,
      manifestSha256: input.manifestSha256,
      requestHash: input.requestHash,
      requestId: input.requestId,
      sessionId: input.sessionId,
      turnId: input.turnId,
    };
    const token = await new SignJWT({ ...claims })
      .setProtectedHeader({
        alg: signingKey.algorithm,
        kid: signingKey.kid,
        typ: 'vfbiz-ai+jwt',
      })
      .sign(signingKey.privateKey);
    return Object.freeze({ expiresAt, jti, kid: signingKey.kid, token });
  }
}

function assertValidInput(input: InternalAiExecutionAssertionInput): void {
  if (input.action !== 'turn.execute' && input.action !== 'turn.cancel') {
    throw new Error('Internal AI assertion action is invalid');
  }
  for (const value of [
    input.requestId,
    input.correlationId,
    input.sessionId,
    input.turnId,
    input.graphRevision,
    input.knowledgeRevision,
    input.policyRevision,
  ]) {
    if (!REVISION_PATTERN.test(value)) {
      throw new Error(
        'Internal AI assertion identifier or revision is invalid',
      );
    }
  }
  for (const value of [
    input.requestId,
    input.correlationId,
    input.sessionId,
    input.turnId,
    input.activationId,
  ]) {
    if (!UUID_PATTERN.test(value)) {
      throw new Error('Internal AI assertion request identity is invalid');
    }
  }
  if (!SHA_256_PATTERN.test(input.manifestSha256)) {
    throw new Error('Internal AI assertion manifest digest is invalid');
  }
  if (!SHA_256_PATTERN.test(input.authorizationContextDigest)) {
    throw new Error(
      'Internal AI assertion authorization context digest is invalid',
    );
  }
  if (!SHA_256_PATTERN.test(input.requestHash)) {
    throw new Error('Internal AI assertion request hash is invalid');
  }
  for (const value of [input.conversationVersion, input.fencingToken]) {
    if (!Number.isSafeInteger(value) || value < 1 || value > MAX_SAFE_INTEGER) {
      throw new Error('Internal AI assertion sequence or fence is invalid');
    }
  }
  if (input.locale !== 'vi' && input.locale !== 'en') {
    throw new Error('Internal AI assertion locale is invalid');
  }
  assertBudget(input);
  assertAuthorization(input.assistantProfile, input.authorization);
}

function assertBudget(input: InternalAiExecutionAssertionInput): void {
  const { budget } = input;
  if (
    !Number.isInteger(budget.maxModelTokens) ||
    budget.maxModelTokens < 1 ||
    budget.maxModelTokens > 32_000 ||
    !Number.isInteger(budget.maxCostMicros) ||
    budget.maxCostMicros < 1 ||
    budget.maxCostMicros > 10_000_000
  ) {
    throw new Error('Internal AI assertion budget is invalid');
  }
  const deadline = Date.parse(budget.deadlineAt);
  if (
    !RFC3339_WITH_TIMEZONE_PATTERN.test(budget.deadlineAt) ||
    !Number.isFinite(deadline) ||
    deadline <= Date.now()
  ) {
    throw new Error('Internal AI assertion deadline is invalid');
  }
}

function assertAuthorization(
  profile: InternalAiExecutionAssertionInput['assistantProfile'],
  authorization: InternalAiAuthorization,
): void {
  if (profile !== 'public_customer' && profile !== 'authenticated_customer') {
    throw new Error('Internal AI assertion assistant profile is invalid');
  }
  if (
    (profile === 'public_customer' &&
      authorization.kind !== 'public_capability') ||
    (profile === 'authenticated_customer' &&
      authorization.kind !== 'authenticated_customer')
  ) {
    throw new Error(
      'Internal AI assertion profile and authorization do not match',
    );
  }
  const tools = authorization.allowedTools;
  if (
    tools.length > (authorization.kind === 'public_capability' ? 1 : 5) ||
    new Set(tools).size !== tools.length ||
    !tools.every((tool) => READ_ONLY_TOOLS.has(tool))
  ) {
    throw new Error('Internal AI assertion tool authorization is invalid');
  }
  if (
    authorization.kind === 'public_capability' &&
    (!SHA_256_PATTERN.test(authorization.capabilityHash) ||
      tools.some((tool) => tool !== 'search_public_knowledge'))
  ) {
    throw new Error('Internal AI public capability is invalid');
  }
  if (authorization.kind === 'authenticated_customer') {
    if (
      !SHA_256_PATTERN.test(authorization.subjectRef) ||
      authorization.scopes.length > 32 ||
      new Set(authorization.scopes).size !== authorization.scopes.length ||
      authorization.scopes.some(
        (scope) =>
          scope.length < 1 ||
          scope.length > 160 ||
          !REVISION_PATTERN.test(scope),
      )
    ) {
      throw new Error('Internal AI customer authorization is invalid');
    }
  }
}

function immutableAuthorization(
  authorization: InternalAiAuthorization,
): InternalAiAuthorization {
  if (authorization.kind === 'public_capability') {
    return Object.freeze({
      ...authorization,
      allowedTools: Object.freeze([...authorization.allowedTools]),
    });
  }
  return Object.freeze({
    ...authorization,
    allowedTools: Object.freeze([...authorization.allowedTools]),
    scopes: Object.freeze([...authorization.scopes]),
  });
}
