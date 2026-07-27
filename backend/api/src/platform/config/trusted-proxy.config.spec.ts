import {
  createFastifyTrustProxy,
  parseTrustedProxyCidrs,
} from './trusted-proxy.config';

describe('trusted proxy configuration', () => {
  it('disables proxy trust by default', () => {
    expect(createFastifyTrustProxy(undefined)).toBe(false);
    expect(createFastifyTrustProxy('')).toBe(false);
  });

  it('trusts only addresses inside explicitly configured IPv4 and IPv6 CIDRs', () => {
    const policy = parseTrustedProxyCidrs(
      '10.20.0.0/16,192.168.4.10/32,2001:db8:42::/48',
    );

    expect(policy.isTrusted('10.20.8.3')).toBe(true);
    expect(policy.isTrusted('::ffff:10.20.8.3')).toBe(true);
    expect(policy.isTrusted('192.168.4.10')).toBe(true);
    expect(policy.isTrusted('2001:db8:42::9')).toBe(true);
    expect(policy.isTrusted('10.21.8.3')).toBe(false);
    expect(policy.isTrusted('203.0.113.5')).toBe(false);
    expect(policy.isTrusted('not-an-ip')).toBe(false);
  });

  it.each(['*', '0.0.0.0/0', '::/0', 'proxy.internal', '10.0.0.1'])(
    'rejects unsafe or non-CIDR entry %s',
    (entry) => {
      expect(() => parseTrustedProxyCidrs(entry)).toThrow();
    },
  );

  it('returns a Fastify callback backed by the parsed allowlist', () => {
    const trustProxy = createFastifyTrustProxy('10.0.0.0/8');
    expect(typeof trustProxy).toBe('function');
    if (typeof trustProxy !== 'function') throw new Error('callback expected');

    expect(trustProxy('10.1.2.3', 0)).toBe(true);
    expect(trustProxy('198.51.100.2', 0)).toBe(false);
  });
});
