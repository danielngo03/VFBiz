import { Module, RequestMethod } from '@nestjs/common';
import { LoggerModule } from 'nestjs-pino';
import { AccessModule } from './modules/access';
import { CustomerModule } from './modules/customer';
import { ProductModule } from './modules/product';
import { PlatformConfigModule } from './platform/config/config.module';
import { PlatformHealthModule } from './platform/health/health.module';
import { PlatformHttpModule } from './platform/http/http.module';
import { PlatformSecurityModule } from './platform/security/security.module';

@Module({
  imports: [
    PlatformConfigModule,
    PlatformHttpModule,
    PlatformSecurityModule,
    LoggerModule.forRoot({
      forRoutes: [{ path: '{*path}', method: RequestMethod.ALL }],
      pinoHttp: {
        level: process.env.VFBIZ_LOG_LEVEL ?? 'info',
        redact: {
          paths: [
            'req.headers.authorization',
            'req.headers.cookie',
            'res.headers.set-cookie',
            '*.password',
            '*.token',
            '*.vin',
          ],
          censor: '[REDACTED]',
        },
      },
    }),
    PlatformHealthModule,
    AccessModule,
    CustomerModule,
    ProductModule,
  ],
})
export class AppModule {}
