export const APPROVED_SOURCE_PLACEHOLDERS = Object.freeze({
  licenseId: 'UNVERIFIED',
  ownerRef: 'unassigned',
  provenanceUri: 'urn:vfbiz:unverified',
  submittedByRef: 'unassigned',
});

export interface SourceRevisionEvidence {
  readonly approvalEvidenceRef: string | null;
  readonly approvalState: 'approved' | 'pending' | 'rejected' | 'retired';
  readonly approvedAt: Date | null;
  readonly approvedByRef: string | null;
  readonly checksum: string;
  readonly classification:
    'public' | 'internal' | 'confidential' | 'restricted';
  readonly effectiveAt: Date;
  readonly expiresAt: Date | null;
  readonly freshnessTtlSeconds: number;
  readonly ingestedAt: Date;
  readonly licenseId: string;
  readonly observedAt: Date;
  readonly ownerRef: string;
  readonly permittedPurposes: readonly string[];
  readonly provenanceUri: string;
  readonly retiredAt: Date | null;
  readonly submittedByRef: string;
}

export class SourceRevisionNotEligibleError extends Error {
  constructor(readonly reason: string) {
    super(`Source revision is not eligible: ${reason}.`);
    this.name = 'SourceRevisionNotEligibleError';
  }
}

export function assertSourceRevisionEligible(
  source: SourceRevisionEvidence,
  purpose: string,
  now: Date,
): void {
  if (source.approvalState !== 'approved') {
    throw new SourceRevisionNotEligibleError('approval is missing');
  }
  if (source.classification !== 'public') {
    throw new SourceRevisionNotEligibleError(
      'classification is not publishable',
    );
  }
  if (
    source.ownerRef === APPROVED_SOURCE_PLACEHOLDERS.ownerRef ||
    source.submittedByRef === APPROVED_SOURCE_PLACEHOLDERS.submittedByRef ||
    source.licenseId === APPROVED_SOURCE_PLACEHOLDERS.licenseId ||
    source.provenanceUri === APPROVED_SOURCE_PLACEHOLDERS.provenanceUri
  ) {
    throw new SourceRevisionNotEligibleError('placeholder governance metadata');
  }
  if (
    source.approvedByRef === null ||
    source.approvedAt === null ||
    source.approvalEvidenceRef === null
  ) {
    throw new SourceRevisionNotEligibleError('approval evidence is incomplete');
  }
  if (source.approvedByRef === source.submittedByRef) {
    throw new SourceRevisionNotEligibleError('separation of duties failed');
  }
  if (!/^[a-f0-9]{64}$/i.test(source.checksum)) {
    throw new SourceRevisionNotEligibleError('checksum is invalid');
  }
  if (!source.permittedPurposes.includes(purpose)) {
    throw new SourceRevisionNotEligibleError('purpose is not permitted');
  }
  if (
    source.freshnessTtlSeconds <= 0 ||
    source.effectiveAt.getTime() > now.getTime() ||
    source.observedAt.getTime() > now.getTime() ||
    source.ingestedAt.getTime() > now.getTime() ||
    source.ingestedAt.getTime() < source.observedAt.getTime() ||
    (source.approvedAt !== null &&
      source.approvedAt.getTime() > now.getTime()) ||
    source.retiredAt !== null ||
    (source.expiresAt !== null && source.expiresAt.getTime() <= now.getTime())
  ) {
    throw new SourceRevisionNotEligibleError('source is not current');
  }
  if (
    source.observedAt.getTime() + source.freshnessTtlSeconds * 1000 <
    now.getTime()
  ) {
    throw new SourceRevisionNotEligibleError('source is stale');
  }
}
