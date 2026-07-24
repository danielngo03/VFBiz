import type { PrismaService } from '../database/prisma.service';
import type { AccessPrincipal } from './access-principal';
import { LocalSessionStatusVerifier } from './local-session-status.verifier';

const principal: AccessPrincipal = {
  authenticationContext: null,
  authenticationMethods: [],
  audience: ['vfbiz-api'],
  authorizedParty: 'vfbiz-customer-bff',
  issuer: 'https://id.example/realms/customer',
  realm: 'customer',
  scopes: [],
  sessionId: 'opaque-session',
  subject: 'customer-1',
};

describe('LocalSessionStatusVerifier', () => {
  it('denies a locally revoked session before the request reaches a controller', async () => {
    const prisma = {
      sessionProjection: {
        findUnique: jest.fn().mockResolvedValue({
          expiresAt: new Date('2026-07-24T00:00:00Z'),
          revokedAt: new Date('2026-07-23T10:00:00Z'),
        }),
      },
    } as unknown as PrismaService;

    await expect(
      new LocalSessionStatusVerifier(prisma).isDenied(
        principal,
        new Date('2026-07-23T11:00:00Z'),
      ),
    ).resolves.toBe(true);
  });
});
