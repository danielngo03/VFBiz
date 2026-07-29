const DIGEST = /^[a-f0-9]{64}$/;
const IDENTIFIER = /^[a-z][a-z0-9_.-]{0,63}$/;
const REVISION = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$/;
const OPAQUE_REFERENCE =
  /^(vehicle|market|locale|profile|garage|policy|product|account):[a-z0-9][a-z0-9._/-]{0,143}$/;
const MAX_TASK_SLOTS = 16;

export type ConversationTaskState =
  'active' | 'awaiting_clarification' | 'closed' | 'expired';

export interface ConversationTaskReleaseBinding {
  readonly activationId: string;
  readonly graphRevision: string;
  readonly knowledgeRevision: string;
  readonly manifestSha256: string;
  readonly policyRevision: string;
}

export interface ConversationTaskSlotReference {
  readonly authorityDigest: string;
  readonly kind: 'opaque_reference';
  readonly reference: string;
}

export interface ConversationTaskContext {
  readonly authorizationContextDigest: string;
  readonly closedAt: Date | null;
  readonly collectedSlots: Readonly<
    Record<string, ConversationTaskSlotReference>
  >;
  readonly expiresAt: Date;
  readonly intent: string;
  readonly intentRevision: string;
  readonly lastFencingToken: number;
  readonly pendingSlots: readonly string[];
  readonly provenanceDigest: string;
  readonly release: ConversationTaskReleaseBinding;
  readonly sourceTurnId: string | null;
  readonly state: ConversationTaskState;
  readonly taskId: string;
  readonly taskVersion: number;
}

export interface ConversationTaskDelta {
  readonly authorizationContextDigest: string;
  readonly collectedSlots: Readonly<
    Record<string, ConversationTaskSlotReference>
  >;
  readonly expectedTaskVersion: number;
  readonly expiresAt: Date;
  readonly intent: string;
  readonly intentRevision: string;
  readonly nextState: Exclude<ConversationTaskState, 'expired'>;
  readonly operation: 'close' | 'upsert';
  readonly pendingSlots: readonly string[];
  readonly provenanceDigest: string;
  readonly release: ConversationTaskReleaseBinding;
  readonly sourceTurnId: string;
  readonly taskId: string;
}

export function assertConversationTaskDelta(
  delta: ConversationTaskDelta,
): void {
  if (
    !Number.isSafeInteger(delta.expectedTaskVersion) ||
    delta.expectedTaskVersion < 0 ||
    (delta.operation === 'close' && delta.nextState !== 'closed') ||
    (delta.operation === 'upsert' && delta.nextState === 'closed')
  ) {
    throw new TypeError('Invalid conversation task delta transition.');
  }
  const candidate: ConversationTaskContext = {
    authorizationContextDigest: delta.authorizationContextDigest,
    closedAt: delta.nextState === 'closed' ? new Date(0) : null,
    collectedSlots: delta.collectedSlots,
    expiresAt: delta.expiresAt,
    intent: delta.intent,
    intentRevision: delta.intentRevision,
    lastFencingToken: 0,
    pendingSlots: delta.pendingSlots,
    provenanceDigest: delta.provenanceDigest,
    release: delta.release,
    sourceTurnId: delta.sourceTurnId,
    state: delta.nextState,
    taskId: delta.taskId,
    taskVersion: Math.max(1, delta.expectedTaskVersion),
  };
  assertConversationTaskContext(candidate);
}

export class ConversationTaskConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = ConversationTaskConflictError.name;
  }
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

function isValidDate(value: Date): boolean {
  return value instanceof Date && Number.isFinite(value.getTime());
}

function assertReleaseBinding(binding: ConversationTaskReleaseBinding): void {
  if (
    !REVISION.test(binding.activationId) ||
    !REVISION.test(binding.graphRevision) ||
    !REVISION.test(binding.knowledgeRevision) ||
    !DIGEST.test(binding.manifestSha256) ||
    !REVISION.test(binding.policyRevision)
  ) {
    throw new TypeError('Invalid conversation task release binding.');
  }
}

function assertTaskSlots(
  pendingSlots: readonly string[],
  collectedSlots: Readonly<Record<string, ConversationTaskSlotReference>>,
): void {
  if (
    !Array.isArray(pendingSlots) ||
    pendingSlots.length > MAX_TASK_SLOTS ||
    !isPlainRecord(collectedSlots) ||
    Object.keys(collectedSlots).length > MAX_TASK_SLOTS
  ) {
    throw new TypeError('Invalid conversation task slots.');
  }

  const pending = new Set<string>();
  for (const slot of pendingSlots) {
    if (
      typeof slot !== 'string' ||
      !IDENTIFIER.test(slot) ||
      pending.has(slot)
    ) {
      throw new TypeError('Invalid pending conversation task slot.');
    }
    pending.add(slot);
  }

  for (const [slot, reference] of Object.entries(collectedSlots)) {
    if (
      !IDENTIFIER.test(slot) ||
      pending.has(slot) ||
      !isPlainRecord(reference) ||
      Object.keys(reference).sort().join(',') !==
        'authorityDigest,kind,reference' ||
      reference.kind !== 'opaque_reference' ||
      typeof reference.reference !== 'string' ||
      !OPAQUE_REFERENCE.test(reference.reference) ||
      typeof reference.authorityDigest !== 'string' ||
      !DIGEST.test(reference.authorityDigest)
    ) {
      throw new TypeError('Invalid collected conversation task slot.');
    }
  }
}

export function assertConversationTaskContext(
  context: ConversationTaskContext,
): void {
  if (
    !REVISION.test(context.taskId) ||
    !IDENTIFIER.test(context.intent) ||
    !REVISION.test(context.intentRevision) ||
    !Number.isSafeInteger(context.taskVersion) ||
    context.taskVersion < 1 ||
    !Number.isSafeInteger(context.lastFencingToken) ||
    context.lastFencingToken < 0 ||
    !DIGEST.test(context.authorizationContextDigest) ||
    !DIGEST.test(context.provenanceDigest) ||
    !isValidDate(context.expiresAt) ||
    (context.sourceTurnId !== null && !REVISION.test(context.sourceTurnId))
  ) {
    throw new TypeError('Invalid conversation task context.');
  }
  if (
    (context.state === 'active' ||
      context.state === 'awaiting_clarification') &&
    context.closedAt !== null
  ) {
    throw new TypeError('Active conversation task cannot be closed.');
  }
  if (
    (context.state === 'closed' || context.state === 'expired') &&
    (context.closedAt === null || !isValidDate(context.closedAt))
  ) {
    throw new TypeError('Terminal conversation task requires closedAt.');
  }
  assertReleaseBinding(context.release);
  assertTaskSlots(context.pendingSlots, context.collectedSlots);
}

function releaseBindingsMatch(
  left: ConversationTaskReleaseBinding,
  right: ConversationTaskReleaseBinding,
): boolean {
  return (
    left.activationId === right.activationId &&
    left.graphRevision === right.graphRevision &&
    left.knowledgeRevision === right.knowledgeRevision &&
    left.manifestSha256 === right.manifestSha256 &&
    left.policyRevision === right.policyRevision
  );
}

export function applyConversationTaskDelta(
  current: ConversationTaskContext,
  delta: ConversationTaskDelta,
  input: { readonly fencingToken: number; readonly now: Date },
): ConversationTaskContext {
  assertConversationTaskDelta(delta);
  assertConversationTaskContext(current);
  if (!isValidDate(input.now) || !Number.isSafeInteger(input.fencingToken)) {
    throw new TypeError('Invalid conversation task transition authority.');
  }
  if (
    current.state === 'closed' ||
    current.state === 'expired' ||
    current.expiresAt.getTime() <= input.now.getTime()
  ) {
    throw new ConversationTaskConflictError(
      'Conversation task is no longer active.',
    );
  }
  if (
    delta.taskId !== current.taskId ||
    delta.expectedTaskVersion !== current.taskVersion ||
    input.fencingToken <= current.lastFencingToken
  ) {
    throw new ConversationTaskConflictError(
      'Conversation task OCC or fencing authority is stale.',
    );
  }
  if (
    delta.authorizationContextDigest !== current.authorizationContextDigest ||
    !releaseBindingsMatch(delta.release, current.release)
  ) {
    throw new ConversationTaskConflictError(
      'Conversation task authority binding changed.',
    );
  }
  if (
    (delta.operation === 'close' && delta.nextState !== 'closed') ||
    (delta.operation === 'upsert' && delta.nextState === 'closed')
  ) {
    throw new TypeError('Invalid conversation task operation.');
  }

  const next: ConversationTaskContext = {
    authorizationContextDigest: delta.authorizationContextDigest,
    closedAt: delta.nextState === 'closed' ? new Date(input.now) : null,
    collectedSlots: delta.collectedSlots,
    expiresAt: new Date(delta.expiresAt),
    intent: delta.intent,
    intentRevision: delta.intentRevision,
    lastFencingToken: input.fencingToken,
    pendingSlots: [...delta.pendingSlots],
    provenanceDigest: delta.provenanceDigest,
    release: { ...delta.release },
    sourceTurnId: delta.sourceTurnId,
    state: delta.nextState,
    taskId: delta.taskId,
    taskVersion: current.taskVersion + 1,
  };
  assertConversationTaskContext(next);
  if (
    next.state !== 'closed' &&
    next.expiresAt.getTime() <= input.now.getTime()
  ) {
    throw new TypeError('Conversation task expiry must be in the future.');
  }
  return next;
}

export function createConversationTaskContext(
  delta: ConversationTaskDelta,
  input: { readonly fencingToken: number; readonly now: Date },
): ConversationTaskContext {
  assertConversationTaskDelta(delta);
  if (
    delta.expectedTaskVersion !== 0 ||
    delta.operation !== 'upsert' ||
    delta.nextState === 'closed'
  ) {
    throw new ConversationTaskConflictError(
      'Initial conversation task delta is not creatable.',
    );
  }
  if (
    !isValidDate(input.now) ||
    !Number.isSafeInteger(input.fencingToken) ||
    input.fencingToken < 1
  ) {
    throw new TypeError('Invalid conversation task creation authority.');
  }
  const context: ConversationTaskContext = {
    authorizationContextDigest: delta.authorizationContextDigest,
    closedAt: null,
    collectedSlots: delta.collectedSlots,
    expiresAt: new Date(delta.expiresAt),
    intent: delta.intent,
    intentRevision: delta.intentRevision,
    lastFencingToken: input.fencingToken,
    pendingSlots: [...delta.pendingSlots],
    provenanceDigest: delta.provenanceDigest,
    release: { ...delta.release },
    sourceTurnId: delta.sourceTurnId,
    state: delta.nextState,
    taskId: delta.taskId,
    taskVersion: 1,
  };
  assertConversationTaskContext(context);
  if (context.expiresAt.getTime() <= input.now.getTime()) {
    throw new TypeError('Conversation task expiry must be in the future.');
  }
  return context;
}
