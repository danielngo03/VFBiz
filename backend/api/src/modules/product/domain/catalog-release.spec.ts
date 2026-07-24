import {
  activateCatalogRelease,
  approveCatalogRelease,
  CatalogReleaseTransitionError,
  restoreCatalogRelease,
  supersedeCatalogRelease,
  type CatalogReleaseStateView,
} from './catalog-release';

const now = new Date('2026-07-24T06:00:00.000Z');
const draft: CatalogReleaseStateView = {
  activatedAt: null,
  activatedByRef: null,
  approvalEvidenceRef: null,
  approvedAt: null,
  approvedByRef: null,
  id: 'release-1',
  market: 'VN',
  revision: 0,
  state: 'draft',
  submittedByRef: 'operator-1',
  supersededAt: null,
};

describe('Catalog release state machine', () => {
  it('approves, activates, supersedes and restores with monotonic revision', () => {
    const approval = approveCatalogRelease(
      draft,
      'data-owner',
      'evidence://release/review-1',
      now,
    );
    const approved = { ...draft, ...approval };
    expect(approved).toMatchObject({ revision: 1, state: 'approved' });

    const activation = activateCatalogRelease(approved, 'release-owner', now);
    const active = { ...approved, ...activation };
    expect(active).toMatchObject({ revision: 2, state: 'active' });

    const supersession = supersedeCatalogRelease(active, now);
    const superseded = { ...active, ...supersession };
    expect(superseded).toMatchObject({ revision: 3, state: 'superseded' });

    expect(
      restoreCatalogRelease(superseded, 'release-owner', now),
    ).toMatchObject({
      revision: 4,
      state: 'active',
      supersededAt: null,
    });
  });

  it('enforces separation of duties', () => {
    expect(() =>
      approveCatalogRelease(
        draft,
        draft.submittedByRef,
        'evidence://release/review-1',
        now,
      ),
    ).toThrow(CatalogReleaseTransitionError);
    expect(() =>
      approveCatalogRelease(
        draft,
        draft.submittedByRef,
        'evidence://release/review-1',
        now,
      ),
    ).toThrow('submitter');
  });

  it('rejects out-of-order transitions', () => {
    expect(() => activateCatalogRelease(draft, 'release-owner', now)).toThrow(
      'must be approved',
    );
    expect(() => supersedeCatalogRelease(draft, now)).toThrow('must be active');
  });

  it('rejects incomplete approval evidence before activation', () => {
    expect(() =>
      activateCatalogRelease(
        { ...draft, state: 'approved' },
        'release-owner',
        now,
      ),
    ).toThrow('evidence');
  });
});
