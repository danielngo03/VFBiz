export type IdentityRealm = 'customer' | 'workforce';

export interface AccessPrincipal {
  readonly subject: string;
  readonly issuer: string;
  readonly audience: readonly string[];
  readonly authorizedParty: string;
  readonly realm: IdentityRealm;
  /**
   * Verified realm roles when the issuer emits a role claim. Older service
   * principals and customer-only test doubles may omit the claim.
   */
  readonly roles?: readonly string[];
  readonly scopes: readonly string[];
  readonly sessionId: string | null;
  readonly authenticationContext: string | null;
  readonly authenticationMethods: readonly string[];
  /**
   * Verified OIDC email_verified claim. Undefined means the identity provider
   * did not issue the claim; callers must not infer that the email is verified.
   */
  readonly emailVerified?: boolean;
  /**
   * Verified OIDC auth_time when available. Privileged authorization fails
   * closed when this value is absent or older than its configured max age.
   */
  readonly authenticatedAt?: Date;
}

export interface VerifiedAccessPrincipal extends AccessPrincipal {
  readonly issuedAt: Date;
  readonly expiresAt: Date;
}
