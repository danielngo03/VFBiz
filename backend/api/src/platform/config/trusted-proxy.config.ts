import { BlockList, isIP } from 'node:net';
import { config as loadDotEnv } from 'dotenv';
import type { FastifyServerOptions } from 'fastify';

const MAX_TRUSTED_PROXY_CIDRS = 64;

interface ParsedCidr {
  readonly address: string;
  readonly family: 'ipv4' | 'ipv6';
  readonly prefix: number;
}

export interface TrustedProxyPolicy {
  readonly cidrs: readonly string[];
  readonly isTrusted: (address: string) => boolean;
}

/**
 * ConfigModule cannot validate `.env` until after the Fastify adapter exists.
 * Load the same local files first so the adapter's trust boundary and the
 * application environment are derived from identical inputs.
 */
export function loadApiBootstrapEnvironment(): void {
  if (process.env.NODE_ENV === 'production') return;
  loadDotEnv({
    path: ['backend/api/.env', '.env'],
    override: false,
    quiet: true,
  });
}

export function parseTrustedProxyCidrs(rawValue: string): TrustedProxyPolicy {
  const rawCidrs = rawValue
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);
  if (rawCidrs.length > MAX_TRUSTED_PROXY_CIDRS) {
    throw new Error(
      `trusted proxy allowlist cannot contain more than ${MAX_TRUSTED_PROXY_CIDRS} CIDRs`,
    );
  }

  const blockList = new BlockList();
  const cidrs: string[] = [];
  for (const rawCidr of rawCidrs) {
    const parsed = parseCidr(rawCidr);
    blockList.addSubnet(parsed.address, parsed.prefix, parsed.family);
    cidrs.push(rawCidr);
  }

  return Object.freeze({
    cidrs: Object.freeze(cidrs),
    isTrusted: (address: string): boolean => {
      const normalized = normalizeRemoteAddress(address);
      if (normalized === undefined) return false;
      return blockList.check(normalized.address, normalized.family);
    },
  });
}

export function createFastifyTrustProxy(
  rawValue: string | undefined,
): FastifyServerOptions['trustProxy'] {
  const policy = parseTrustedProxyCidrs(rawValue ?? '');
  if (policy.cidrs.length === 0) return false;
  return (address: string): boolean => policy.isTrusted(address);
}

function parseCidr(rawCidr: string): ParsedCidr {
  if (rawCidr === '*' || !rawCidr.includes('/')) {
    throw new Error(
      `trusted proxy entry "${rawCidr}" must be an explicit IPv4 or IPv6 CIDR`,
    );
  }
  const separator = rawCidr.lastIndexOf('/');
  const address = rawCidr.slice(0, separator);
  const rawPrefix = rawCidr.slice(separator + 1);
  if (address.includes('%') || !/^\d+$/.test(rawPrefix)) {
    throw new Error(`trusted proxy entry "${rawCidr}" is not a valid CIDR`);
  }
  const ipVersion = isIP(address);
  if (ipVersion === 0) {
    throw new Error(`trusted proxy entry "${rawCidr}" is not a valid CIDR`);
  }
  const prefix = Number(rawPrefix);
  const maximumPrefix = ipVersion === 4 ? 32 : 128;
  if (prefix <= 0 || prefix > maximumPrefix) {
    throw new Error(
      `trusted proxy entry "${rawCidr}" has an unsafe or invalid prefix`,
    );
  }
  return {
    address,
    family: ipVersion === 4 ? 'ipv4' : 'ipv6',
    prefix,
  };
}

function normalizeRemoteAddress(
  rawAddress: string,
): { readonly address: string; readonly family: 'ipv4' | 'ipv6' } | undefined {
  const address = rawAddress.replace(/^\[|\]$/g, '').split('%', 1)[0];
  const mappedIpv4 = /^::ffff:(\d{1,3}(?:\.\d{1,3}){3})$/i.exec(address)?.[1];
  if (mappedIpv4 !== undefined && isIP(mappedIpv4) === 4) {
    return { address: mappedIpv4, family: 'ipv4' };
  }
  const ipVersion = isIP(address);
  if (ipVersion === 4) return { address, family: 'ipv4' };
  if (ipVersion === 6) return { address, family: 'ipv6' };
  return undefined;
}
