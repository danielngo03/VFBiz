import { Injectable, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { PrismaPg } from '@prisma/adapter-pg';
import { PrismaClient } from '../../generated/prisma/client';

@Injectable()
export class PrismaService
  extends PrismaClient
  implements OnModuleInit, OnModuleDestroy
{
  private readonly connectOnModuleInit: boolean;

  constructor(config: ConfigService) {
    const adapter = new PrismaPg(
      config.getOrThrow<string>('VFBIZ_DATABASE_URL'),
    );
    super({ adapter });
    this.connectOnModuleInit = config.getOrThrow<string>('NODE_ENV') !== 'test';
  }

  async onModuleInit(): Promise<void> {
    if (this.connectOnModuleInit) await this.$connect();
  }

  async onModuleDestroy(): Promise<void> {
    await this.$disconnect();
  }
}
