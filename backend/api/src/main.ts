import { ConfigService } from '@nestjs/config';
import { NestFactory } from '@nestjs/core';
import {
  FastifyAdapter,
  NestFastifyApplication,
} from '@nestjs/platform-fastify';
import { Logger } from 'nestjs-pino';
import { AppModule } from './app.module';
import { configureApplication } from './bootstrap/configure-application';
import {
  createFastifyTrustProxy,
  loadApiBootstrapEnvironment,
} from './platform/config/trusted-proxy.config';
import { configureOpenApi } from './platform/openapi/openapi';
import { configureWorkforceOpenApi } from './platform/openapi/workforce-openapi';

async function bootstrap() {
  loadApiBootstrapEnvironment();
  const app = await NestFactory.create<NestFastifyApplication>(
    AppModule,
    new FastifyAdapter({
      trustProxy: createFastifyTrustProxy(
        process.env.VFBIZ_API_TRUSTED_PROXY_CIDRS,
      ),
    }),
    { bufferLogs: true },
  );
  const config = app.get(ConfigService);
  app.useLogger(app.get(Logger));
  await configureApplication(app);
  if (config.getOrThrow<boolean>('VFBIZ_API_DOCS_ENABLED')) {
    configureOpenApi(app);
  }
  if (config.getOrThrow<boolean>('VFBIZ_WORKFORCE_API_DOCS_ENABLED')) {
    configureWorkforceOpenApi(app);
  }

  await app.listen({
    host: config.getOrThrow<string>('VFBIZ_API_HOST'),
    port: config.getOrThrow<number>('VFBIZ_API_PORT'),
  });
}
void bootstrap();
