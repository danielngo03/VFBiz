import { Injectable } from '@nestjs/common';
import { PrismaService } from '../database/prisma.service';
import type { AccessPrincipal } from './access-principal';
import { sessionReferenceFingerprint } from './session-reference-fingerprint';

@Injectable()
export class LocalSessionStatusVerifier {
  constructor(private readonly prisma: PrismaService) {}

  async isDenied(
    principal: AccessPrincipal,
    now = new Date(),
  ): Promise<boolean> {
    if (principal.realm !== 'customer' || principal.sessionId === null) {
      return false;
    }
    const session = await this.prisma.sessionProjection.findUnique({
      select: { expiresAt: true, revokedAt: true },
      where: {
        sessionRefHash: sessionReferenceFingerprint(
          principal,
          principal.sessionId,
        ),
      },
    });
    return (
      session !== null &&
      (session.revokedAt !== null ||
        session.expiresAt.getTime() <= now.getTime())
    );
  }
}
