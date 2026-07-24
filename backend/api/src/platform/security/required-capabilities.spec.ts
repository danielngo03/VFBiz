import {
  isRequiredCapabilitiesPolicy,
  RequireCapabilities,
} from './required-capabilities';

describe('RequireCapabilities', () => {
  it('accepts atomic resource actions and removes duplicates', () => {
    expect(
      isRequiredCapabilitiesPolicy({
        mode: 'all-of',
        capabilities: ['authorization.role.read'],
      }),
    ).toBe(true);
    expect(() =>
      RequireCapabilities({
        mode: 'all-of',
        capabilities: ['authorization.role.read', 'authorization.role.read'],
      }),
    ).not.toThrow();
  });

  it('rejects wildcard and malformed capability policies', () => {
    expect(
      isRequiredCapabilitiesPolicy({
        mode: 'any-of',
        capabilities: ['*'],
      }),
    ).toBe(false);
    expect(() =>
      RequireCapabilities({ mode: 'all-of', capabilities: [] }),
    ).toThrow(TypeError);
  });
});
