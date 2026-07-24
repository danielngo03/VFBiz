import { Module } from '@nestjs/common';
import { DatabaseModule } from '../../platform/database/database.module';
import { ProductModule } from '../product';
import { AccessModule } from '../access';
import { CustomerAccountRepository } from './application/ports/customer-account.repository';
import { CustomerAccountService } from './application/services/customer-account.service';
import { CustomerGarageRepository } from './application/ports/customer-garage.repository';
import { CustomerGarageService } from './application/services/customer-garage.service';
import { PrismaCustomerAccountRepository } from './infrastructure/persistence/prisma-customer-account.repository';
import { PrismaCustomerGarageRepository } from './infrastructure/persistence/prisma-customer-garage.repository';
import { CustomerController } from './presentation/customer.controller';
import { CustomerGarageController } from './presentation/customer-garage.controller';
import { WorkforceCustomerSupportController } from './presentation/workforce-customer-support.controller';
import { WorkforceCustomerSupportService } from './application/services/workforce-customer-support.service';
import { WorkforceCustomerSupportRepository } from './application/ports/workforce-customer-support.repository';
import { PrismaWorkforceCustomerSupportRepository } from './infrastructure/persistence/prisma-workforce-customer-support.repository';

@Module({
  controllers: [
    CustomerController,
    CustomerGarageController,
    WorkforceCustomerSupportController,
  ],
  imports: [AccessModule, DatabaseModule, ProductModule],
  providers: [
    CustomerAccountService,
    {
      provide: CustomerAccountRepository,
      useClass: PrismaCustomerAccountRepository,
    },
    CustomerGarageService,
    {
      provide: CustomerGarageRepository,
      useClass: PrismaCustomerGarageRepository,
    },
    WorkforceCustomerSupportService,
    {
      provide: WorkforceCustomerSupportRepository,
      useClass: PrismaWorkforceCustomerSupportRepository,
    },
  ],
})
export class CustomerModule {}
