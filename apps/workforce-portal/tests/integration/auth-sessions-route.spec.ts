import {beforeEach, describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({
  cookies: vi.fn(),
  deleteSubjectSessions: vi.fn(),
  listSubjectSessions: vi.fn(),
  readSession: vi.fn(),
  revokeOidcSession: vi.fn(),
}));

vi.mock('next/headers', () => ({cookies: mocks.cookies}));
vi.mock('@/platform/config/environment', () => ({
  readWorkforcePortalEnvironment: () => ({
    WORKFORCE_SESSION_COOKIE_NAME: 'vfbiz_workforce_session',
  }),
}));
vi.mock('@/platform/auth/oidc', () => ({
  revokeOidcSession: mocks.revokeOidcSession,
}));
vi.mock('@/platform/session/redis-token-vault', () => ({
  deleteSubjectSessions: mocks.deleteSubjectSessions,
  listSubjectSessions: mocks.listSubjectSessions,
  readSession: mocks.readSession,
}));

import {DELETE, GET} from '@/app/api/auth/sessions/route';

const currentSession = {
  authenticatedAt: '2026-07-24T08:00:00.000Z',
  deviceLabel: 'Chrome on macOS',
  emailVerified: true,
  expiresAt: '2026-07-24T18:00:00.000Z',
  id: 'session-current',
  lastSeenAt: '2026-07-24T09:00:00.000Z',
  mfaSatisfied: true,
  networkHint: '203.0.113.0/24',
  subject: 'workforce-subject-1',
  userAgentSummary: 'Chrome 140 on macOS',
};

const currentRecord = {
  session: currentSession,
  tokenSet: {
    accessToken: 'access-secret-current',
    expiresAt: '2026-07-24T09:10:00.000Z',
    refreshToken: 'refresh-secret-current',
  },
};

describe('workforce session routes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.cookies.mockResolvedValue({
      get: vi.fn().mockReturnValue({value: currentSession.id}),
    });
    mocks.readSession.mockResolvedValue(currentRecord);
    mocks.listSubjectSessions.mockResolvedValue([
      currentRecord,
      {
        session: {...currentSession, id: 'session-other'},
        tokenSet: {
          ...currentRecord.tokenSet,
          refreshToken: 'refresh-secret-other',
        },
      },
    ]);
    mocks.revokeOidcSession.mockResolvedValue(undefined);
    mocks.deleteSubjectSessions.mockResolvedValue(2);
  });

  it('lists minimized devices without returning token material', async () => {
    const response = await GET();
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(response.headers.get('cache-control')).toBe('private, no-store');
    expect(body).toHaveLength(2);
    expect(body[0]).toMatchObject({
      id: 'session-current',
      isCurrent: true,
      networkHint: '203.0.113.0/24',
    });
    expect(JSON.stringify(body)).not.toContain('access-secret');
    expect(JSON.stringify(body)).not.toContain('refresh-secret');
  });

  it('revokes every indexed provider session before deleting the local index', async () => {
    const response = await DELETE(
      new Request('https://workforce.example/api/auth/sessions', {
        headers: {origin: 'https://workforce.example'},
        method: 'DELETE',
      }),
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({revokedCount: 2});
    expect(mocks.revokeOidcSession).toHaveBeenCalledTimes(2);
    expect(mocks.revokeOidcSession).toHaveBeenNthCalledWith(
      1,
      'refresh-secret-current',
    );
    expect(mocks.revokeOidcSession).toHaveBeenNthCalledWith(
      2,
      'refresh-secret-other',
    );
    expect(mocks.deleteSubjectSessions).toHaveBeenCalledWith(
      'workforce-subject-1',
    );
    expect(response.headers.get('set-cookie')).toContain(
      'vfbiz_workforce_session=',
    );
  });

  it('rejects a cross-origin logout before reading the session', async () => {
    const response = await DELETE(
      new Request('https://workforce.example/api/auth/sessions', {
        headers: {origin: 'https://attacker.example'},
        method: 'DELETE',
      }),
    );

    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({error: 'invalid_origin'});
    expect(mocks.readSession).not.toHaveBeenCalled();
    expect(mocks.deleteSubjectSessions).not.toHaveBeenCalled();
  });
});
