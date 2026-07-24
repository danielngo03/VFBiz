import { Injectable } from '@nestjs/common';
import type {
  AccessPrincipal,
  VerifiedAccessPrincipal,
} from '../../../../platform/security/access-principal';
import {
  assertValidObservation,
  MissingSessionReferenceError,
  type SessionClientContext,
  type ReconcileSessionObservation,
  type CustomerIdentitySecurityView,
  type RevokeAllSessionsView,
  type RevokeSessionView,
} from '../../domain/access-session';
import { AccessSessionRepository } from '../ports/access-session.repository';
import { CiamSessionRevocationPort } from '../ports/ciam-session-revocation.port';

@Injectable()
export class AccessSessionService {
  constructor(
    private readonly repository: AccessSessionRepository,
    private readonly ciam: CiamSessionRevocationPort,
  ) {}

  list(principal: AccessPrincipal, now = new Date()) {
    return this.repository.list(principal, now);
  }

  async revoke(
    principal: AccessPrincipal,
    projectionId: string,
    now = new Date(),
  ): Promise<RevokeSessionView> {
    const revocation = await this.repository.beginRevocation(
      principal,
      projectionId,
      now,
    );
    if (!revocation.dispatch) {
      return {
        reconciliation: revocation.reconciliation,
        session: revocation.session,
      };
    }
    let reconciliation:
      'confirmed' | 'manual_review_required' | 'retry_required';
    try {
      reconciliation = await this.ciam.revoke({
        providerRoute: revocation.providerRoute!,
        providerSessionSecretReference:
          revocation.providerSessionSecretReference!,
      });
    } catch {
      reconciliation = 'retry_required';
    }
    await this.repository.completeRevocation(
      projectionId,
      revocation.revocationVersion,
      reconciliation,
      now,
    );
    return { reconciliation, session: revocation.session };
  }

  reconcile(observation: ReconcileSessionObservation, now = new Date()) {
    assertValidObservation(observation, now);
    return this.repository.reconcile(observation, now);
  }

  observeVerifiedPrincipal(
    principal: VerifiedAccessPrincipal,
    client: SessionClientContext = {
      deviceLabel: null,
      ipPrefix: null,
      userAgentSummary: null,
    },
    now = new Date(),
  ) {
    if (principal.realm !== 'customer' || principal.sessionId === null) {
      throw new MissingSessionReferenceError();
    }
    return this.reconcile(
      {
        authenticatedAt: principal.authenticatedAt,
        authorizedParty: principal.authorizedParty,
        deviceLabel: client.deviceLabel,
        emailVerified: principal.emailVerified ?? null,
        eventRevision:
          BigInt(principal.expiresAt.getTime()) * 1_000_000n +
          BigInt(principal.issuedAt.getTime()),
        expiresAt: principal.expiresAt,
        issuer: principal.issuer,
        ipPrefix: client.ipPrefix,
        lastSeenAt: now,
        mfaSatisfied: principal.authenticationMethods.some((method) =>
          ['otp', 'mfa', 'webauthn'].includes(method),
        ),
        observedAt: now,
        providerRoute: 'customer-ciam',
        providerSessionSecretReference: null,
        realm: 'customer',
        revokedAt: null,
        sessionReference: principal.sessionId,
        subject: principal.subject,
        userAgentSummary: client.userAgentSummary,
      },
      now,
    );
  }

  revokeCurrent(principal: AccessPrincipal, now = new Date()) {
    return this.repository.revokeCurrent(principal, now);
  }

  async revokeAll(
    principal: AccessPrincipal,
    now = new Date(),
  ): Promise<RevokeAllSessionsView> {
    const locallyRevokedCount = await this.repository.revokeAll(principal, now);
    let reconciliation:
      'confirmed' | 'manual_review_required' | 'retry_required';
    try {
      reconciliation = await this.ciam.revokeAll({
        issuer: principal.issuer,
        subject: principal.subject,
      });
    } catch {
      reconciliation = 'retry_required';
    }
    return { locallyRevokedCount, reconciliation };
  }

  async securityStatus(
    principal: AccessPrincipal,
  ): Promise<CustomerIdentitySecurityView> {
    const provider = await this.ciam.securityStatus({
      issuer: principal.issuer,
      subject: principal.subject,
    });
    return {
      currentSessionMfaSatisfied: principal.authenticationMethods.some(
        (method) => ['otp', 'mfa', 'webauthn'].includes(method),
      ),
      emailVerified: provider?.emailVerified ?? principal.emailVerified ?? null,
      mfaConfigured: provider?.mfaConfigured ?? null,
      providerStatus: provider === null ? 'unavailable' : 'available',
    };
  }
}
