import {readWorkforcePortalEnvironment} from '@/platform/config/environment';

export interface WorkforceClientContext {
  readonly deviceLabel: string | null;
  readonly networkHint: string | null;
  readonly userAgentSummary: string | null;
}

function networkHint(value: string | null): string | null {
  if (value === null) return null;
  const first = value.split(',')[0]?.trim() ?? '';
  const match = first.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.\d{1,3}$/);
  if (match !== null) return `${match[1]}.${match[2]}.${match[3]}.0/24`;
  if (first.includes(':')) {
    const groups = first.split(':').filter(Boolean).slice(0, 4);
    return groups.length > 0 ? `${groups.join(':')}::/64` : null;
  }
  return null;
}

export function workforceClientContext(request: Request): WorkforceClientContext {
  const raw = request.headers.get('user-agent');
  const userAgentSummary = raw?.slice(0, 255) ?? null;
  const browser = /Edg\//i.test(raw ?? '')
    ? 'Edge'
    : /Chrome\//i.test(raw ?? '')
      ? 'Chrome'
      : /Firefox\//i.test(raw ?? '')
        ? 'Firefox'
        : /Safari\//i.test(raw ?? '')
          ? 'Safari'
          : 'Browser';
  const platform = /Windows/i.test(raw ?? '')
    ? 'Windows'
    : /Macintosh|Mac OS X/i.test(raw ?? '')
      ? 'macOS'
      : /Android/i.test(raw ?? '')
        ? 'Android'
        : /iPhone|iPad/i.test(raw ?? '')
          ? 'iOS'
          : 'Unknown device';
  return {
    deviceLabel: raw === null ? null : `${browser} on ${platform}`,
    networkHint: readWorkforcePortalEnvironment().WORKFORCE_TRUST_PROXY_HEADERS
      ? networkHint(request.headers.get('x-forwarded-for'))
      : null,
    userAgentSummary,
  };
}
