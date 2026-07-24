import { ValidationPipe, VersioningType } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import compress from '@fastify/compress';
import helmet from '@fastify/helmet';
import type { NestFastifyApplication } from '@nestjs/platform-fastify';
import { ProblemDetailsFilter } from '../platform/http/problem-details.filter';
import {
  RequestWithContext,
  resolveCorrelationId,
} from '../platform/http/request-context';

export async function configureApplication(
  application: NestFastifyApplication,
): Promise<void> {
  const configuration = application.get(ConfigService);
  application.enableShutdownHooks();
  application.enableVersioning({
    type: VersioningType.URI,
    defaultVersion: '1',
    prefix: 'api/v',
  });
  application.useGlobalPipes(
    new ValidationPipe({
      forbidNonWhitelisted: true,
      transform: true,
      whitelist: true,
    }),
  );
  application.useGlobalFilters(new ProblemDetailsFilter());
  const server = application.getHttpAdapter().getInstance();
  server.addHook('onRequest', async (request, reply) => {
    const correlationId = resolveCorrelationId(request);
    (request as RequestWithContext).vfbizCorrelationId = correlationId;
    void reply.header('x-correlation-id', correlationId);
  });
  await application.register(helmet, {
    hsts:
      configuration.getOrThrow<string>('NODE_ENV') === 'production'
        ? { maxAge: 31_536_000, includeSubDomains: true }
        : false,
  });
  await application.register(compress, { encodings: ['gzip', 'deflate'] });
}
