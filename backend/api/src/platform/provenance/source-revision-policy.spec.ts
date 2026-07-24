import {
  assertSourceRevisionEligible,
  SourceRevisionNotEligibleError,
  type SourceRevisionEvidence,
} from './source-revision-policy';

const now = new Date('2026-07-23T12:00:00.000Z');
const eligible: SourceRevisionEvidence = {
  approvalEvidenceRef: 'evidence://vehicle-data/review-42',
  approvalState: 'approved',
  approvedAt: new Date('2026-07-23T11:00:00.000Z'),
  approvedByRef: 'data-owner-2',
  checksum: 'a'.repeat(64),
  classification: 'public',
  effectiveAt: new Date('2026-07-23T00:00:00.000Z'),
  expiresAt: new Date('2026-07-24T00:00:00.000Z'),
  freshnessTtlSeconds: 86_400,
  ingestedAt: new Date('2026-07-23T10:00:01.000Z'),
  licenseId: 'PROPRIETARY-VINFAST-APPROVED',
  observedAt: new Date('2026-07-23T10:00:00.000Z'),
  ownerRef: 'vehicle-data-owner',
  permittedPurposes: ['vehicle-catalog'],
  provenanceUri: 'urn:vfbiz:source:pim:release-42',
  retiredAt: null,
  submittedByRef: 'vehicle-data-operator-1',
};

describe('source revision eligibility', () => {
  it('accepts approved, current evidence for its permitted purpose', () => {
    expect(() =>
      assertSourceRevisionEligible(eligible, 'vehicle-catalog', now),
    ).not.toThrow();
  });

  it.each([
    [{ ...eligible, approvalState: 'pending' as const }, 'approval'],
    [{ ...eligible, classification: 'internal' as const }, 'classification'],
    [{ ...eligible, licenseId: 'UNVERIFIED' }, 'placeholder'],
    [{ ...eligible, approvedByRef: eligible.submittedByRef }, 'separation'],
    [{ ...eligible, permittedPurposes: ['trip-planning'] }, 'purpose'],
    [
      {
        ...eligible,
        observedAt: new Date('2026-07-20T00:00:00.000Z'),
      },
      'stale',
    ],
  ])('rejects ineligible source evidence', (source, reason) => {
    expect(() =>
      assertSourceRevisionEligible(source, 'vehicle-catalog', now),
    ).toThrow(SourceRevisionNotEligibleError);
    expect(() =>
      assertSourceRevisionEligible(source, 'vehicle-catalog', now),
    ).toThrow(reason);
  });
});
