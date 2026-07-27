import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { validateEnvironment } from './env.schema';
import { loadApiBootstrapEnvironment } from './trusted-proxy.config';

loadApiBootstrapEnvironment();

@Module({
  imports: [
    ConfigModule.forRoot({
      cache: true,
      envFilePath: ['backend/api/.env', '.env'],
      expandVariables: false,
      ignoreEnvFile: process.env.NODE_ENV === 'production',
      isGlobal: true,
      validate: validateEnvironment,
    }),
  ],
  exports: [ConfigModule],
})
export class PlatformConfigModule {}
