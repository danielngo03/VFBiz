import { DSAR_TARGET_SET_REVISION, dsarTargetPlan } from './customer-account';

describe('DSAR target plan', () => {
  it('keeps identity available until every dependent delete target finishes', () => {
    const targets = dsarTargetPlan('delete');
    const identity = targets.find((target) => target.key === 'access-identity');
    const latestDependentPhase = Math.max(
      ...targets
        .filter((target) => target.key !== 'access-identity')
        .map((target) => target.phase),
    );

    expect(DSAR_TARGET_SET_REVISION).toBe('dsar-targets-v2');
    expect(identity?.phase).toBeGreaterThan(latestDependentPhase);
  });

  it('captures identity before exporting dependent customer data', () => {
    const targets = dsarTargetPlan('export');
    const identity = targets.find((target) => target.key === 'access-identity');

    expect(identity?.phase).toBe(1);
    expect(new Set(targets.map((target) => target.key)).size).toBe(8);
  });
});
