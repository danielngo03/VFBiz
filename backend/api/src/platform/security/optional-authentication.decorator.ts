import { SetMetadata } from '@nestjs/common';

export const OPTIONAL_AUTHENTICATION = 'vfbiz:optional-authentication';

export const OptionalAuthentication = () =>
  SetMetadata(OPTIONAL_AUTHENTICATION, true);
