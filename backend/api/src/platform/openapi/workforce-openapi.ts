import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { NestFastifyApplication } from '@nestjs/platform-fastify';
import { apiReference } from '@scalar/nestjs-api-reference';

const workforceContractPath = '/api-docs/workforce/openapi.yaml';
const workforceReferencePath = '/reference/workforce';
const scalarFavicon =
  'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22%3E%3Crect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%237c3aed%22/%3E%3Cpath d=%22M15 17h9l8 21 8-21h9L36 49h-8z%22 fill=%22white%22/%3E%3C/svg%3E';

function resolveWorkforceContract(): string {
  const candidates = [
    resolve(process.cwd(), 'contracts/openapi/workforce-v1.yaml'),
    resolve(process.cwd(), '../../contracts/openapi/workforce-v1.yaml'),
  ];
  const contract = candidates.find((candidate) => existsSync(candidate));
  if (contract === undefined) {
    throw new Error(
      'Unable to locate contracts/openapi/workforce-v1.yaml from the current working directory.',
    );
  }
  return contract;
}

export function configureWorkforceOpenApi(
  application: NestFastifyApplication,
): void {
  const contract = readFileSync(resolveWorkforceContract(), 'utf8');
  const fastify = application.getHttpAdapter().getInstance();

  fastify.get(workforceContractPath, (_request, reply) =>
    reply
      .header('Cache-Control', 'private, no-store')
      .header('Content-Disposition', 'inline; filename="workforce-v1.yaml"')
      .header('X-Content-Type-Options', 'nosniff')
      .type('application/yaml; charset=utf-8')
      .send(contract),
  );

  application.use(
    workforceReferencePath,
    apiReference({
      agent: { disabled: true },
      darkMode: true,
      defaultHttpClient: { targetKey: 'shell', clientKey: 'curl' },
      defaultOpenAllTags: true,
      defaultOpenFirstTag: true,
      documentDownloadType: 'direct',
      favicon: scalarFavicon,
      hideDarkModeToggle: false,
      hideTestRequestButton: true,
      layout: 'modern',
      modelsSectionLabel: 'Schemas',
      operationTitleSource: 'summary',
      pageTitle: 'VFBiz Workforce API Reference',
      persistAuth: false,
      showDeveloperTools: 'never',
      showOperationId: false,
      showSidebar: true,
      theme: 'default',
      url: workforceContractPath,
      withFastify: true,
    }),
  );
}
