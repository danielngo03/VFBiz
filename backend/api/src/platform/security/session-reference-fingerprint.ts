import { createHash } from 'node:crypto';

export interface SessionReferenceIdentity {
  readonly authorizedParty: string;
  readonly issuer: string;
  readonly subject: string;
}

export function sessionReferenceFingerprint(
  identity: SessionReferenceIdentity,
  sessionReference: string,
): string {
  return createHash('sha256')
    .update(
      JSON.stringify({
        authorizedParty: identity.authorizedParty,
        issuer: identity.issuer,
        sessionReference,
        subject: identity.subject,
      }),
      'utf8',
    )
    .digest('hex');
}
