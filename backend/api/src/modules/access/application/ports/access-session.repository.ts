import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import type {
  AccessSessionView,
  ReconcileSessionObservation,
  SessionRevocationReconciliation,
} from '../../domain/access-session';

export interface BeginSessionRevocationResult {
  readonly dispatch: boolean;
  readonly providerRoute: 'customer-ciam' | null;
  readonly providerSessionSecretReference: string | null;
  readonly revocationVersion: number;
  readonly reconciliation: SessionRevocationReconciliation;
  readonly session: AccessSessionView;
}

export abstract class AccessSessionRepository {
  abstract list(
    principal: AccessPrincipal,
    now: Date,
  ): Promise<readonly AccessSessionView[]>;

  abstract beginRevocation(
    principal: AccessPrincipal,
    projectionId: string,
    revokedAt: Date,
  ): Promise<BeginSessionRevocationResult>;

  abstract completeRevocation(
    projectionId: string,
    revocationVersion: number,
    reconciliation: Exclude<SessionRevocationReconciliation, 'pending'>,
    completedAt: Date,
  ): Promise<void>;

  abstract reconcile(
    observation: ReconcileSessionObservation,
    now: Date,
  ): Promise<AccessSessionView>;

  abstract revokeCurrent(
    principal: AccessPrincipal,
    revokedAt: Date,
  ): Promise<void>;

  abstract revokeAll(
    principal: AccessPrincipal,
    revokedAt: Date,
  ): Promise<number>;
}
