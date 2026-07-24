export type CiamSessionRevocationOutcome =
  'confirmed' | 'manual_review_required' | 'retry_required';

export interface CiamSessionRevocationCommand {
  readonly providerRoute: 'customer-ciam';
  readonly providerSessionSecretReference: string;
}

export interface CiamSubjectCommand {
  readonly issuer: string;
  readonly subject: string;
}

export interface CiamIdentitySecurityStatus {
  readonly emailVerified: boolean;
  readonly mfaConfigured: boolean;
}

export abstract class CiamSessionRevocationPort {
  abstract revoke(
    command: CiamSessionRevocationCommand,
  ): Promise<CiamSessionRevocationOutcome>;

  abstract revokeAll(
    command: CiamSubjectCommand,
  ): Promise<CiamSessionRevocationOutcome>;

  abstract securityStatus(
    command: CiamSubjectCommand,
  ): Promise<CiamIdentitySecurityStatus | null>;
}
