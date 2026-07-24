const CHAT_CAPABILITY_COOKIE = '__Host-vfbiz_chat';

function parseCookieHeader(header: string | undefined): Map<string, string> {
  const values = new Map<string, string>();
  if (header === undefined) return values;
  for (const segment of header.split(';')) {
    const separator = segment.indexOf('=');
    if (separator <= 0) continue;
    const name = segment.slice(0, separator).trim();
    const value = segment.slice(separator + 1).trim();
    if (name.length > 0) values.set(name, value);
  }
  return values;
}

export function buildConversationCapabilityCookie(
  sessionId: string,
  capability: string,
  maxAgeSeconds: number,
): string {
  if (!Number.isSafeInteger(maxAgeSeconds) || maxAgeSeconds <= 0) {
    throw new Error('Conversation capability cookie max age must be positive.');
  }
  return `${CHAT_CAPABILITY_COOKIE}=${sessionId}.${capability}; Max-Age=${maxAgeSeconds}; Path=/; HttpOnly; Secure; SameSite=Lax`;
}

export function clearConversationCapabilityCookie(): string {
  return `${CHAT_CAPABILITY_COOKIE}=; Max-Age=0; Path=/; HttpOnly; Secure; SameSite=Lax`;
}

export function readConversationCapabilityCookie(
  header: string | undefined,
  requestedSessionId: string,
): string | null {
  const value = parseCookieHeader(header).get(CHAT_CAPABILITY_COOKIE);
  if (value === undefined) return null;
  const separator = value.indexOf('.');
  if (separator <= 0 || separator === value.length - 1) return null;
  const sessionId = value.slice(0, separator);
  const capability = value.slice(separator + 1);
  if (sessionId !== requestedSessionId || capability.includes('.')) return null;
  return capability;
}
