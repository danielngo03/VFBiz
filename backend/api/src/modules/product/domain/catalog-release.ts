export type CatalogReleaseState =
  'draft' | 'approved' | 'active' | 'superseded' | 'rejected';

export interface CatalogReleaseStateView {
  readonly activatedAt: Date | null;
  readonly activatedByRef: string | null;
  readonly approvalEvidenceRef: string | null;
  readonly approvedAt: Date | null;
  readonly approvedByRef: string | null;
  readonly id: string;
  readonly market: string;
  readonly revision: number;
  readonly state: CatalogReleaseState;
  readonly submittedByRef: string;
  readonly supersededAt: Date | null;
}

export interface CatalogReleaseStatePatch {
  readonly activatedAt?: Date | null;
  readonly activatedByRef?: string | null;
  readonly approvalEvidenceRef?: string;
  readonly approvedAt?: Date;
  readonly approvedByRef?: string;
  readonly revision: number;
  readonly state: CatalogReleaseState;
  readonly supersededAt?: Date | null;
}

export class CatalogReleaseTransitionError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = 'CatalogReleaseTransitionError';
  }
}

function nonBlank(value: string, field: string): string {
  const normalized = value.trim();
  if (normalized.length === 0) {
    throw new CatalogReleaseTransitionError(
      'INVALID_RELEASE_EVIDENCE',
      `${field} is required.`,
    );
  }
  return normalized;
}

function assertState(
  release: CatalogReleaseStateView,
  expected: CatalogReleaseState,
): void {
  if (release.state !== expected) {
    throw new CatalogReleaseTransitionError(
      'INVALID_RELEASE_STATE',
      `Release ${release.id} must be ${expected}, received ${release.state}.`,
    );
  }
}

function nextRevision(release: CatalogReleaseStateView): number {
  if (!Number.isSafeInteger(release.revision) || release.revision < 0) {
    throw new CatalogReleaseTransitionError(
      'INVALID_RELEASE_REVISION',
      'Release revision is invalid.',
    );
  }
  return release.revision + 1;
}

export function approveCatalogRelease(
  release: CatalogReleaseStateView,
  reviewerRef: string,
  evidenceRef: string,
  now: Date,
): CatalogReleaseStatePatch {
  assertState(release, 'draft');
  const reviewer = nonBlank(reviewerRef, 'reviewerRef');
  if (reviewer === release.submittedByRef) {
    throw new CatalogReleaseTransitionError(
      'SEPARATION_OF_DUTIES_REQUIRED',
      'Release submitter cannot approve the same release.',
    );
  }
  return {
    approvalEvidenceRef: nonBlank(evidenceRef, 'evidenceRef'),
    approvedAt: now,
    approvedByRef: reviewer,
    revision: nextRevision(release),
    state: 'approved',
  };
}

export function activateCatalogRelease(
  release: CatalogReleaseStateView,
  actorRef: string,
  now: Date,
): CatalogReleaseStatePatch {
  assertState(release, 'approved');
  if (
    release.approvedByRef === null ||
    release.approvedAt === null ||
    release.approvalEvidenceRef === null
  ) {
    throw new CatalogReleaseTransitionError(
      'INVALID_RELEASE_EVIDENCE',
      'Approved release evidence is incomplete.',
    );
  }
  return {
    activatedAt: now,
    activatedByRef: nonBlank(actorRef, 'actorRef'),
    revision: nextRevision(release),
    state: 'active',
    supersededAt: null,
  };
}

export function supersedeCatalogRelease(
  release: CatalogReleaseStateView,
  now: Date,
): CatalogReleaseStatePatch {
  assertState(release, 'active');
  return {
    revision: nextRevision(release),
    state: 'superseded',
    supersededAt: now,
  };
}

export function restoreCatalogRelease(
  release: CatalogReleaseStateView,
  actorRef: string,
  now: Date,
): CatalogReleaseStatePatch {
  assertState(release, 'superseded');
  if (
    release.approvedByRef === null ||
    release.approvedAt === null ||
    release.approvalEvidenceRef === null
  ) {
    throw new CatalogReleaseTransitionError(
      'INVALID_RELEASE_EVIDENCE',
      'Superseded release evidence is incomplete.',
    );
  }
  return {
    activatedAt: now,
    activatedByRef: nonBlank(actorRef, 'actorRef'),
    revision: nextRevision(release),
    state: 'active',
    supersededAt: null,
  };
}
