import {
  assertProductSourceCandidate,
  ProductSourceCandidateError,
  type ProductSourceCandidate,
} from './product-source-candidate';

const pendingCandidate: ProductSourceCandidate = {
  aiTrainingAllowed: false,
  approvalEvidenceRef: null,
  approvedByRef: null,
  documentCode: 'VF-PRICE-2026-07',
  documentIssuedAt: '2026-07-11T00:00:00+07:00',
  expectedSha256: null,
  factValidityMode: 'single-window',
  id: 'product-source:vinfast-vn-price-2026-07',
  market: 'VN',
  permittedPurposes: [],
  publisher: 'VinFast',
  rightsState: 'pending',
  sourceKind: 'official-public-document',
  sourceUrl: 'https://example.com/price.pdf',
  submittedByRef: 'product-data-operator',
  title: 'Official price policy',
};

describe('Product source candidate', () => {
  it('accepts pending metadata without treating it as approved', () => {
    expect(() => assertProductSourceCandidate(pendingCandidate)).not.toThrow();
  });

  it.each([
    [
      { ...pendingCandidate, sourceUrl: 'http://example.com/price.pdf' },
      'HTTPS',
    ],
    [
      {
        ...pendingCandidate,
        permittedPurposes: ['ai-training'],
      },
      'training',
    ],
    [
      {
        ...pendingCandidate,
        approvalEvidenceRef: 'evidence://unexpected',
      },
      'unapproved',
    ],
    [
      {
        ...pendingCandidate,
        approvalEvidenceRef: 'evidence://data-owner/review-1',
        approvedByRef: 'product-data-operator',
        expectedSha256: 'a'.repeat(64),
        permittedPurposes: ['vehicle-catalog'],
        rightsState: 'approved' as const,
      },
      'submitter',
    ],
  ])('rejects unsafe registry metadata', (candidate, reason) => {
    expect(() => assertProductSourceCandidate(candidate)).toThrow(
      ProductSourceCandidateError,
    );
    expect(() => assertProductSourceCandidate(candidate)).toThrow(reason);
  });

  it('accepts an independently approved source with immutable evidence', () => {
    expect(() =>
      assertProductSourceCandidate({
        ...pendingCandidate,
        approvalEvidenceRef: 'evidence://data-owner/review-1',
        approvedByRef: 'data-owner',
        expectedSha256: 'a'.repeat(64),
        permittedPurposes: ['vehicle-catalog'],
        rightsState: 'approved',
      }),
    ).not.toThrow();
  });
});
