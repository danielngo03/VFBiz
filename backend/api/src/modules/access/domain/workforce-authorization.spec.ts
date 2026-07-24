import {
  isScopeValid,
  scopeAllows,
  type AuthorizationScope,
} from './workforce-authorization';

describe('workforce authorization scope policy', () => {
  it.each([
    [{ type: 'global', ref: 'global' }, true],
    [{ type: 'market', ref: 'vn' }, true],
    [{ type: 'showroom', ref: 'showroom-hn-01' }, true],
    [{ type: 'department', ref: 'customer-care' }, true],
    [{ type: 'global', ref: 'vn' }, false],
    [{ type: 'market', ref: 'global' }, false],
    [{ type: 'showroom', ref: '' }, false],
    [{ type: 'unknown', ref: 'anything' }, false],
  ])('validates %o as %s', (scope, expected) => {
    expect(isScopeValid(scope as AuthorizationScope)).toBe(expected);
  });

  it('allows a global grant for any requested organizational scope', () => {
    expect(
      scopeAllows([{ type: 'global', ref: 'global' }], {
        type: 'showroom',
        ref: 'showroom-hn-01',
      }),
    ).toBe(true);
  });

  it('requires an exact match for a scoped grant', () => {
    const grants: AuthorizationScope[] = [{ type: 'market', ref: 'vn' }];

    expect(scopeAllows(grants, { type: 'market', ref: 'vn' })).toBe(true);
    expect(scopeAllows(grants, { type: 'market', ref: 'us' })).toBe(false);
    expect(scopeAllows(grants)).toBe(false);
  });
});
