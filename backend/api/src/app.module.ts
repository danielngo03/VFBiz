import { Module, RequestMethod } from '@nestjs/common';
import { LoggerModule } from 'nestjs-pino';
import { ConversationContextIntegrationModule } from './integration/conversation/conversation-context-integration.module';
import { AccessModule } from './modules/access';
import { CustomerModule } from './modules/customer';
import { EngagementRuntimeModule } from './modules/engagement/engagement-runtime.module';
import { EngagementModule } from './modules/engagement/engagement.module';
import { PlatformConfigModule } from './platform/config/config.module';
import { PlatformHealthModule } from './platform/health/health.module';
import { PlatformHttpModule } from './platform/http/http.module';
import { PlatformSecurityModule } from './platform/security/security.module';

const engagementComposition =
  process.env.VFBIZ_CHAT_API_MODE === 'authenticated-staging'
    ? EngagementModule
    : EngagementRuntimeModule;

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
    ConversationContextIntegrationModule,
    engagementComposition,
  ],
})
export class AppModule {}
