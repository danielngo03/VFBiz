import { Module } from '@nestjs/common';
import { APP_GUARD } from '@nestjs/core';
import { DatabaseModule } from '../database/database.module';
import { AuthenticationGuard } from './authentication.guard';
import { AuthenticationAssuranceGuard } from './authentication-assurance.guard';
import { IdentityRealmGuard } from './identity-realm.guard';
import { LocalSessionStatusVerifier } from './local-session-status.verifier';
import { OidcJwksProvider } from './oidc-jwks.provider';
import { OidcTokenVerifier } from './oidc-token.verifier';
import { OidcTrustPolicy } from './oidc-trust-policy';
import { ScopeAuthorizationGuard } from './scope-authorization.guard';
import { RoleAuthorizationGuard } from './role-authorization.guard';

@Module({
  imports: [DatabaseModule],
  providers: [
    LocalSessionStatusVerifier,
    OidcJwksProvider,
    OidcTokenVerifier,
    OidcTrustPolicy,
    { provide: APP_GUARD, useClass: AuthenticationGuard },
    { provide: APP_GUARD, useClass: AuthenticationAssuranceGuard },
    { provide: APP_GUARD, useClass: IdentityRealmGuard },
    { provide: APP_GUARD, useClass: ScopeAuthorizationGuard },
    { provide: APP_GUARD, useClass: RoleAuthorizationGuard },
  ],
  exports: [LocalSessionStatusVerifier, OidcTokenVerifier, OidcTrustPolicy],
})
export class PlatformSecurityModule {}
