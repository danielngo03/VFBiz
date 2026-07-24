import { writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter, NestFastifyApplication } from '@nestjs/platform-fastify';
import { configureApplication } from '../src/bootstrap/configure-application';
import { createOpenApiDocument } from '../src/platform/openapi/openapi';

// Contract assembly must not require a live PostgreSQL connection.
process.env.NODE_ENV = 'test';

async function exportOpenApi(): Promise<void> {
  const { AppModule } = await import('../src/app.module.js');
  const application = await NestFactory.create<NestFastifyApplication>(
    AppModule,
    new FastifyAdapter(),
    { abortOnError: false, logger: false },
  );
  await configureApplication(application);
  await application.init();
  const document = createOpenApiDocument(application);
  const requestedOutput = process.argv[2] ?? '/tmp/vfbiz-public-v1.openapi.json';
  const output = resolve(requestedOutput);
  await writeFile(output, `${JSON.stringify(document, null, 2)}\n`, 'utf8');
  await application.close();
  process.stdout.write(`${output}\n`);
}

void exportOpenApi().catch((error: unknown) => {
  const message = error instanceof Error ? error.stack : String(error);
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
