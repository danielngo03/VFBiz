export type ProductSourceKind =
  'official-public-document' | 'pim-export' | 'erp-export';

export type ProductSourceRightsState = 'pending' | 'approved' | 'rejected';

export interface ProductSourceCandidate {
  readonly aiTrainingAllowed: false;
  readonly approvalEvidenceRef: string | null;
  readonly approvedByRef: string | null;
  readonly documentCode: string;
  readonly documentIssuedAt: string | null;
  readonly expectedSha256: string | null;
  readonly factValidityMode: 'single-window' | 'per-fact';
  readonly id: string;
  readonly market: string;
  readonly permittedPurposes: readonly string[];
  readonly publisher: string;
  readonly rightsState: ProductSourceRightsState;
  readonly sourceKind: ProductSourceKind;
  readonly sourceUrl: string;
  readonly submittedByRef: string;
  readonly title: string;
}

export class ProductSourceCandidateError extends Error {
  constructor(
    readonly candidateId: string,
    readonly reason: string,
  ) {
    super(`Product source candidate ${candidateId} is invalid: ${reason}.`);
    this.name = 'ProductSourceCandidateError';
  }
}

const sha256Pattern = /^[a-f0-9]{64}$/i;
const marketPattern = /^[A-Z]{2}$/;
const safeDocumentCodePattern = /^[A-Za-z0-9._-]{3,160}$/;

function fail(candidate: ProductSourceCandidate, reason: string): never {
  throw new ProductSourceCandidateError(candidate.id, reason);
}

/**
 * Validates registry metadata only. Network fetch and database import remain
 * separate operations so a pending source can never become publishable by
 * merely appearing in the repository.
 */
export function assertProductSourceCandidate(
  candidate: ProductSourceCandidate,
): void {
  if (!candidate.id.startsWith('product-source:')) {
    fail(candidate, 'id must use the product-source namespace');
  }
  if (
    candidate.title.trim().length === 0 ||
    candidate.publisher.trim().length === 0
  ) {
    fail(candidate, 'title and publisher are required');
  }
  if (!marketPattern.test(candidate.market)) {
    fail(candidate, 'market must be an ISO 3166-1 alpha-2 code');
  }
  if (!safeDocumentCodePattern.test(candidate.documentCode)) {
    fail(candidate, 'document code is invalid');
  }

  let sourceUrl: URL;
  try {
    sourceUrl = new URL(candidate.sourceUrl);
  } catch {
    fail(candidate, 'source URL is invalid');
  }
  if (sourceUrl.protocol !== 'https:') {
    fail(candidate, 'source URL must use HTTPS');
  }
  if (
    candidate.documentIssuedAt !== null &&
    Number.isNaN(Date.parse(candidate.documentIssuedAt))
  ) {
    fail(candidate, 'documentIssuedAt must be an ISO date-time');
  }
  if (candidate.aiTrainingAllowed !== false) {
    fail(candidate, 'product source candidates cannot authorize AI training');
  }
  if (candidate.permittedPurposes.includes('ai-training')) {
    fail(candidate, 'AI training purpose is forbidden');
  }
  if (candidate.submittedByRef.trim().length === 0) {
    fail(candidate, 'submitter is required');
  }

  if (candidate.rightsState !== 'approved') {
    if (
      candidate.approvedByRef !== null ||
      candidate.approvalEvidenceRef !== null
    ) {
      fail(candidate, 'unapproved source cannot carry approval evidence');
    }
    return;
  }

  if (
    candidate.expectedSha256 === null ||
    !sha256Pattern.test(candidate.expectedSha256)
  ) {
    fail(candidate, 'approved source requires a SHA-256 checksum');
  }
  if (
    candidate.approvedByRef === null ||
    candidate.approvalEvidenceRef === null
  ) {
    fail(candidate, 'approved source requires independent approval evidence');
  }
  if (candidate.approvedByRef === candidate.submittedByRef) {
    fail(candidate, 'submitter cannot approve the same source');
  }
  if (!candidate.permittedPurposes.includes('vehicle-catalog')) {
    fail(candidate, 'vehicle-catalog purpose is required');
  }
}
