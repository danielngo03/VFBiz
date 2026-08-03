export type StagingChatLiveControlClosedReason =
  | 'invalid-expectation'
  | 'clock-rollback'
  | 'not-yet-valid'
  | 'expired'
  | 'missing'
  | 'malformed'
  | 'mismatched'
  | 'release-missing'
  | 'release-mismatched'
  | 'disabled'
  | 'unavailable';

export interface StagingChatLiveControlExpectation {
  readonly authorityDigest: string;
  readonly controlId: string;
  readonly expiresAt: Date;
  readonly generation: number;
  readonly notBefore: Date;
  readonly releaseEnvelopeSha256: string;
  readonly releasePointerRevision: number;
}

export class StagingChatLiveControlClosedError extends Error {
  constructor(readonly reason: StagingChatLiveControlClosedReason) {
    super('Authenticated staging Chat live control is closed.');
    this.name = StagingChatLiveControlClosedError.name;
  }
}

/**
 * API-owned dispatch liveness. Customer authentication remains a separate
 * earlier boundary; the active release projection is an additional fail-closed
 * binding and never grants customer identity or scope.
 */
export abstract class StagingChatLiveControl {
  abstract assertLive(): Promise<void>;
}

export class ClosedStagingChatLiveControl extends StagingChatLiveControl {
  assertLive(): Promise<void> {
    return Promise.reject(new StagingChatLiveControlClosedError('disabled'));
  }
}
