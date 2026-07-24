import type { FastifyRequest } from 'fastify';
import type { SessionClientContext } from '../domain/access-session';

function ipPrefix(address: string): string | null {
  const normalized = address.trim();
  const ipv4 = normalized.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.\d{1,3}$/);
  if (ipv4 !== null) {
    const octets = ipv4.slice(1).map(Number);
    if (octets.every((octet) => octet >= 0 && octet <= 255)) {
      return `${octets.join('.')}.0/24`;
    }
  }
  if (normalized.includes(':')) {
    const groups = normalized.split(':').filter(Boolean).slice(0, 4);
    return groups.length === 0 ? null : `${groups.join(':')}::/64`;
  }
  return null;
}

function browserLabel(userAgent: string): string {
  if (/Edg\//i.test(userAgent)) return 'Edge';
  if (/Chrome\//i.test(userAgent)) return 'Chrome';
  if (/Firefox\//i.test(userAgent)) return 'Firefox';
  if (/Safari\//i.test(userAgent)) return 'Safari';
  return 'Browser';
}

function platformLabel(userAgent: string): string {
  if (/iPhone|iPad/i.test(userAgent)) return 'iOS';
  if (/Android/i.test(userAgent)) return 'Android';
  if (/Windows/i.test(userAgent)) return 'Windows';
  if (/Macintosh|Mac OS X/i.test(userAgent)) return 'macOS';
  if (/Linux/i.test(userAgent)) return 'Linux';
  return 'Unknown device';
}

export function sessionClientContext(
  request: FastifyRequest,
): SessionClientContext {
  const rawUserAgent = request.headers['user-agent'];
  const userAgent =
    typeof rawUserAgent === 'string'
      ? [...rawUserAgent]
          .filter((character) => {
            const code = character.charCodeAt(0);
            return code > 31 && code !== 127;
          })
          .join('')
          .slice(0, 255)
      : null;
  return {
    deviceLabel:
      userAgent === null
        ? null
        : `${browserLabel(userAgent)} on ${platformLabel(userAgent)}`,
    ipPrefix: ipPrefix(request.ip),
    userAgentSummary: userAgent,
  };
}
