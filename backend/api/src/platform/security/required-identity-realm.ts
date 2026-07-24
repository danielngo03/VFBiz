import { SetMetadata } from '@nestjs/common';
import type { IdentityRealm } from './access-principal';

export const REQUIRED_IDENTITY_REALM = 'vfbiz.requiredIdentityRealm';

export const RequireIdentityRealm = (realm: IdentityRealm) =>
  SetMetadata(REQUIRED_IDENTITY_REALM, realm);
