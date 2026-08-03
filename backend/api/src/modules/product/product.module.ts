import { Module } from '@nestjs/common';
import { DatabaseModule } from '../../platform/database/database.module';
import { CatalogReleaseWorkflowRepository } from './application/ports/catalog-release-workflow.repository';
import { CommercialDataRepository } from './application/ports/commercial-data.repository';
import { CommercialReleaseWorkflowRepository } from './application/ports/commercial-release-workflow.repository';
import { VehicleCatalogRepository } from './application/ports/vehicle-catalog.repository';
import { CatalogReleaseWorkflowService } from './application/services/catalog-release-workflow.service';
import { CheckVehicleVariantEligibilityService } from './application/services/check-vehicle-variant-eligibility.service';
import { CommercialReleaseWorkflowService } from './application/services/commercial-release-workflow.service';
import { ReadCommercialDataService } from './application/services/read-commercial-data.service';
import { ReadVehicleCatalogService } from './application/services/read-vehicle-catalog.service';
import { ResolveVehicleCatalogIdentityService } from './application/services/resolve-vehicle-catalog-identity.service';
import { VehicleCatalogIdentityResolver } from './vehicle-catalog-identity.resolver';
import { PrismaCatalogReleaseWorkflowRepository } from './infrastructure/persistence/prisma-catalog-release-workflow.repository';
import { PrismaCommercialDataRepository } from './infrastructure/persistence/prisma-commercial-data.repository';
import { PrismaCommercialReleaseWorkflowRepository } from './infrastructure/persistence/prisma-commercial-release-workflow.repository';
import { PrismaVehicleCatalogRepository } from './infrastructure/persistence/prisma-vehicle-catalog.repository';
import { VehicleCatalogController } from './presentation/vehicle-catalog.controller';
import { OperationsReleaseController } from './presentation/operations-release.controller';

@Module({
  controllers: [OperationsReleaseController, VehicleCatalogController],
  imports: [DatabaseModule],
  providers: [
    CatalogReleaseWorkflowService,
    CheckVehicleVariantEligibilityService,
    CommercialReleaseWorkflowService,
    ReadCommercialDataService,
    ReadVehicleCatalogService,
    ResolveVehicleCatalogIdentityService,
    {
      provide: VehicleCatalogIdentityResolver,
      useExisting: ResolveVehicleCatalogIdentityService,
    },
    {
      provide: CommercialDataRepository,
      useClass: PrismaCommercialDataRepository,
    },
    {
      provide: CommercialReleaseWorkflowRepository,
      useClass: PrismaCommercialReleaseWorkflowRepository,
    },
    {
      provide: CatalogReleaseWorkflowRepository,
      useClass: PrismaCatalogReleaseWorkflowRepository,
    },
    {
      provide: VehicleCatalogRepository,
      useClass: PrismaVehicleCatalogRepository,
    },
  ],
  exports: [
    CatalogReleaseWorkflowService,
    CheckVehicleVariantEligibilityService,
    CommercialReleaseWorkflowService,
    VehicleCatalogIdentityResolver,
  ],
})
export class ProductModule {}
