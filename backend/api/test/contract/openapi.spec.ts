import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { Test } from '@nestjs/testing';
import {
  FastifyAdapter,
  NestFastifyApplication,
} from '@nestjs/platform-fastify';
import { AppModule } from '../../src/app.module';
import { configureApplication } from '../../src/bootstrap/configure-application';
import {
  configureOpenApi,
  createOpenApiDocument,
} from '../../src/platform/openapi/openapi';
import { configureWorkforceOpenApi } from '../../src/platform/openapi/workforce-openapi';

const HTTP_METHODS = new Set([
  'delete',
  'get',
  'head',
  'options',
  'patch',
  'post',
  'put',
  'trace',
]);

type OperationInventory = Readonly<Record<string, string>>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function runtimePublicInventory(
  document: ReturnType<typeof createOpenApiDocument>,
): OperationInventory {
  const inventory: Record<string, string> = {};
  for (const [path, pathItem] of Object.entries(document.paths)) {
    for (const [method, operation] of Object.entries(
      pathItem as Record<string, unknown>,
    )) {
      if (
        !HTTP_METHODS.has(method) ||
        !isRecord(operation) ||
        typeof operation['operationId'] !== 'string'
      ) {
        continue;
      }
      inventory[operation['operationId']] = `${method.toUpperCase()} ${path}`;
    }
  }
  return inventory;
}

function reviewedPublicInventory(source: string): OperationInventory {
  const pathsStart = source.indexOf('paths:\n');
  const componentsStart = source.indexOf('components:\n');
  const pathsSection =
    pathsStart >= 0 && componentsStart > pathsStart
      ? source.slice(pathsStart, componentsStart)
      : '';
  const inventory: Record<string, string> = {};
  let path: string | undefined;
  let method: string | undefined;

  for (const line of pathsSection.split('\n')) {
    const pathMatch = line.match(/^\s{2}(\/[^:]+):$/);
    if (pathMatch !== null) {
      path = pathMatch[1];
      method = undefined;
      continue;
    }
    const methodMatch = line.match(/^\s{4}([a-z]+):$/);
    if (methodMatch !== null && HTTP_METHODS.has(methodMatch[1])) {
      method = methodMatch[1];
      continue;
    }
    const operationMatch = line.match(/^\s{6}operationId:\s*(\S+)$/);
    if (operationMatch !== null && path !== undefined && method !== undefined) {
      inventory[operationMatch[1]] = `${method.toUpperCase()} ${path}`;
    }
  }
  return inventory;
}

describe('public OpenAPI contract', () => {
  let app: NestFastifyApplication;

  beforeAll(async () => {
    const moduleFixture = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();
    app = moduleFixture.createNestApplication<NestFastifyApplication>(
      new FastifyAdapter(),
    );
    await configureApplication(app);
    configureOpenApi(app);
    configureWorkforceOpenApi(app);
    await app.init();
    await app.getHttpAdapter().getInstance().ready();
  });

  it('exports versioned resource routes with stable operation IDs and bearer authentication', () => {
    const document = createOpenApiDocument(app);

    expect(document.paths['/api/v1/health/live']?.get?.operationId).toBe(
      'liveness',
    );
    expect(document.paths['/api/v1/health/ready']?.get?.operationId).toBe(
      'readiness',
    );
    expect(document.components?.securitySchemes).toHaveProperty(
      'customerAccessToken',
    );
    expect(document.components?.securitySchemes).not.toHaveProperty(
      'customerSession',
    );
    expect(document.components?.securitySchemes).not.toHaveProperty(
      'anonymousChatCapability',
    );
    expect(document.paths['/api/v1/chat/sessions']).toBeUndefined();
    expect(document.paths['/api/v1/trip/plans']).toBeUndefined();
    expect(document.paths['/api/v1/operations/customers']).toBeUndefined();
    expect(
      document.paths[
        '/api/v1/operations/releases/vehicle-catalog/{releaseId}/approve'
      ],
    ).toBeUndefined();
    expect(document.paths['/api/v1/me']?.get?.security).toEqual([
      { customerAccessToken: [] },
    ]);
    expect(document.paths['/api/v1/vehicles/models']?.get?.security).toEqual(
      [],
    );
    expect(document.paths['/auth/customer/login']).toBeUndefined();
    expect(
      Object.keys(document.paths).every((path) => path.startsWith('/api/v1/')),
    ).toBe(true);
  });

  it('serves a separate read-only workforce contract without polluting the public document', async () => {
    const publicDocument = createOpenApiDocument(app);
    expect(
      Object.keys(publicDocument.paths).some((path) =>
        path.startsWith('/api/v1/workforce/'),
      ),
    ).toBe(false);

    const response = await app.inject({
      method: 'GET',
      url: '/api-docs/workforce/openapi.yaml',
    });
    expect(response.statusCode).toBe(200);
    expect(response.headers['cache-control']).toBe('private, no-store');
    expect(response.headers['content-type']).toContain('application/yaml');
    expect(response.body).toContain('title: VFBiz Workforce API');
    expect(response.body).toContain('/api/v1/workforce/me/entitlements:');
    expect(response.body).not.toContain('/auth/customer/login:');
  });

  it('keeps every reviewed public operation aligned with runtime routes', () => {
    const document = createOpenApiDocument(app);
    const reviewedContract = readFileSync(
      resolve(process.cwd(), '../../contracts/openapi/public-v1.yaml'),
      'utf8',
    );

    expect(reviewedPublicInventory(reviewedContract)).toEqual(
      runtimePublicInventory(document),
    );
  });

  it('pins runtime schemas for session and DSAR responses', () => {
    const document = createOpenApiDocument(app);
    const revoke =
      document.paths['/api/v1/me/sessions/{sessionId}']?.delete?.responses;
    expect(revoke).toHaveProperty('200');
    expect(revoke).not.toHaveProperty('204');
    expect(
      document.paths['/api/v1/me/sessions']?.get?.responses?.['200'],
    ).toMatchObject({
      content: {
        'application/json': {
          schema: {
            items: {
              $ref: '#/components/schemas/AccessSessionResponseDto',
            },
            type: 'array',
          },
        },
      },
    });
    expect(
      document.paths['/api/v1/me/data-requests']?.get?.responses?.['200'],
    ).toMatchObject({
      content: {
        'application/json': {
          schema: {
            items: {
              $ref: '#/components/schemas/CustomerDataRequestResponseDto',
            },
            type: 'array',
          },
        },
      },
    });
  });

  it('serves Swagger JSON and Scalar reference from the runtime app', async () => {
    const swagger = await app.inject({
      method: 'GET',
      url: '/api-docs/customer/openapi.json',
    });
    expect(swagger.statusCode).toBe(200);
    const swaggerBody = JSON.parse(swagger.body) as {
      readonly info?: { readonly title?: unknown };
      readonly openapi?: unknown;
    };
    expect(swaggerBody.info?.title).toBe('VFBiz Customer API');
    expect(typeof swaggerBody.openapi).toBe('string');

    const scalar = await app.inject({
      method: 'GET',
      url: '/reference/customer',
    });
    expect(scalar.statusCode).toBe(200);
    expect(scalar.headers['content-type']).toContain('text/html');
    expect(scalar.body).toContain('/api-docs/customer/openapi.json');
    expect(scalar.body).toContain('VFBiz Customer API Reference');

    const workforce = await app.inject({
      method: 'GET',
      url: '/reference/workforce',
    });
    expect(workforce.statusCode).toBe(200);
    expect(workforce.headers['content-type']).toContain('text/html');
    expect(workforce.body).toContain('/api-docs/workforce/openapi.yaml');
    expect(workforce.body).toContain('VFBiz Workforce API Reference');
    expect(workforce.body).not.toContain('/api-docs/customer/openapi.json');

    const legacyReference = await app.inject({
      method: 'GET',
      url: '/reference',
    });
    expect(legacyReference.statusCode).toBe(308);
    expect(legacyReference.headers.location).toBe('/reference/customer');
  });

  afterAll(async () => app.close());
});
