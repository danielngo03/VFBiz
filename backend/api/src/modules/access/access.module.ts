import { Module } from '@nestjs/common';
import { APP_GUARD } from '@nestjs/core';
import { DatabaseModule } from '../../platform/database/database.module';
import { PlatformSecurityModule } from '../../platform/security/security.module';
import { AccessSessionRepository } from './application/ports/access-session.repository';
import { CiamSessionRevocationPort } from './application/ports/ciam-session-revocation.port';
import { IdempotencyRepository } from './application/ports/idempotency.repository';
import { AccessSessionService } from './application/services/access-session.service';
import { AuthorizationDecisionService } from './application/services/authorization-decision.service';
import { WorkforceAuthorizationService } from './application/services/workforce-authorization.service';
import { WorkforceAuthorizationRepository } from './application/ports/workforce-authorization.repository';
import { WorkforceEntitlementReader } from '../../platform/security/workforce-entitlement-reader';
import { KeycloakCiamSessionRevocationAdapter } from './infrastructure/ciam/keycloak-ciam-session-revocation.adapter';
import { PrismaAccessSessionRepository } from './infrastructure/persistence/prisma-access-session.repository';
import { PrismaIdempotencyRepository } from './infrastructure/persistence/prisma-idempotency.repository';
import { PrismaWorkforceAuthorizationRepository } from './infrastructure/persistence/prisma-workforce-authorization.repository';
import { AccessSessionController } from './presentation/access-session.controller';
import { CapabilityAuthorizationGuard } from './presentation/capability-authorization.guard';
import { WorkforceAuthorizationController } from './presentation/workforce-authorization.controller';

@Module({
  controllers: [AccessSessionController, WorkforceAuthorizationController],
  imports: [DatabaseModule, PlatformSecurityModule],
  providers: [
    AccessSessionService,
    AuthorizationDecisionService,
    {
      provide: WorkforceEntitlementReader,
      useExisting: AuthorizationDecisionService,
    },
    WorkforceAuthorizationService,
    {
      provide: APP_GUARD,
      useClass: CapabilityAuthorizationGuard,
    },
    {
      provide: AccessSessionRepository,
      useClass: PrismaAccessSessionRepository,
    },
    {
      provide: CiamSessionRevocationPort,
      useClass: KeycloakCiamSessionRevocationAdapter,
    },
    {
      provide: WorkforceAuthorizationRepository,
      useClass: PrismaWorkforceAuthorizationRepository,
    },
    {
      provide: IdempotencyRepository,
      useClass: PrismaIdempotencyRepository,
    },
  ],
  exports: [WorkforceEntitlementReader],
})
export class AccessModule {}
