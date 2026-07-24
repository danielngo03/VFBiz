import type { NestFastifyApplication } from '@nestjs/platform-fastify';
import type { OpenAPIObject } from '@nestjs/swagger';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import { apiReference } from '@scalar/nestjs-api-reference';

const swaggerPath = 'api-docs/customer';
const openApiJsonPath = `${swaggerPath}/openapi.json`;
const scalarPath = '/reference/customer';
const scalarFavicon =
  'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22%3E%3Crect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%230ea5e9%22/%3E%3Cpath d=%22M15 17h9l8 21 8-21h9L36 49h-8z%22 fill=%22white%22/%3E%3C/svg%3E';

interface OpenApiOperation {
  description?: string;
  operationId?: string;
  responses: Record<string, unknown>;
  security?: Array<Record<string, string[]>>;
  summary?: string;
  tags?: string[];
  [extension: `x-${string}`]: unknown;
}

type HttpMethod =
  'delete' | 'get' | 'head' | 'options' | 'patch' | 'post' | 'put' | 'trace';

type OpenApiPathItem = Partial<Record<HttpMethod, OpenApiOperation>>;

interface MutableOpenApiDocument {
  components?: {
    securitySchemes?: Record<string, unknown>;
  };
  openapi: string;
  info: OpenAPIObject['info'] & { [extension: `x-${string}`]: unknown };
  paths: Record<string, OpenApiPathItem>;
  servers?: Array<{ description?: string; url: string }>;
  tags?: Array<{
    description?: string;
    name: string;
    [extension: `x-${string}`]: unknown;
  }>;
  [extension: `x-${string}`]: unknown;
}

const operationTitles: Readonly<Record<string, string>> = Object.freeze({
  createChatMessage: 'Send a message',
  createChatSession: 'Create chat session',
  createDataRequest: 'Request data export/delete',
  createMyDataRequest: 'Request data export/delete',
  createMyVehicle: 'Add a vehicle',
  deleteMyVehicle: 'Archive vehicle',
  getVehicleModel: 'Get vehicle model',
  getVehicleModelBySlug: 'Get vehicle model',
  getMyProfile: 'Get profile',
  getProfile: 'Get profile',
  liveness: 'Check liveness',
  list: 'List records',
  listChatMessages: 'List chat messages',
  listConsents: 'List consents',
  listMySessions: 'List sessions',
  listMyVehicles: 'List garage',
  listVehicleModels: 'List vehicle models',
  putMyConsent: 'Update consents',
  revoke: 'Revoke session',
  revokeMySession: 'Revoke session',
  updateMyProfile: 'Update profile',
  updateProfile: 'Update profile',
  updateMyVehicle: 'Update vehicle',
});

const operationDescriptions: Readonly<Record<string, string>> = Object.freeze({
  createChatMessage:
    'Accepts one customer message. The endpoint fails closed until an approved AI release manifest is active.',
  createChatSession:
    'Creates a governed chat session for public or authenticated customer use. Anonymous sessions receive an opaque capability cookie.',
  createMyDataRequest:
    'Creates an idempotent privacy request for data export or deletion. The execution worker completes the request asynchronously.',
  createMyVehicle:
    'Adds a self-reported vehicle variant to the customer garage. The vehicle remains unverified until an ownership provider confirms it.',
  deleteMyVehicle:
    'Archives one self-reported garage entry. The operation requires the current garage ETag.',
  getVehicleModelBySlug:
    'Returns one approved public vehicle model projection by stable slug and market.',
  liveness: 'Returns `ok` when the API process is serving local requests.',
  getMyProfile:
    'Returns the current customer profile derived from the verified OIDC subject.',
  listVehicleModels:
    'Returns approved public vehicle model projections for the requested market.',
  listConsents:
    'Returns the latest consent state by purpose without exposing the append-only ledger internals.',
  listMySessions:
    'Lists customer session projections with minimized device metadata. Provider secrets and raw session handles are never returned.',
  listMyVehicles:
    'Lists active garage entries for the current customer subject only.',
  updateMyProfile:
    'Updates editable customer profile preferences using optimistic concurrency via `If-Match`.',
  putMyConsent:
    'Records immutable consent decisions. Reusing an idempotency key for a different request is rejected.',
  revokeMySession:
    'Marks a customer session projection as revoked and denies future local API use for that session.',
  updateMyVehicle:
    'Updates a self-reported garage entry with optimistic concurrency through `If-Match`.',
});

const operationTags: Readonly<Record<string, string>> = Object.freeze({
  listMyVehicles: 'Garage',
  createMyVehicle: 'Garage',
  updateMyVehicle: 'Garage',
  deleteMyVehicle: 'Garage',
});

function operationEntries(document: MutableOpenApiDocument) {
  const methods: readonly HttpMethod[] = [
    'delete',
    'get',
    'patch',
    'post',
    'put',
  ];
  return Object.entries(document.paths).flatMap(([path, item]) =>
    methods.flatMap((method) => {
      const operation = item[method];
      return operation === undefined ? [] : [{ method, operation, path }];
    }),
  );
}

function mergeResponse(
  operation: OpenApiOperation,
  code: string,
  description: string,
): void {
  operation.responses ??= {};
  operation.responses[code] ??= { description };
}

function polishOperation(
  entry: ReturnType<typeof operationEntries>[number],
): void {
  const { method, operation, path } = entry;
  const id = operation.operationId;
  if (id !== undefined) {
    operation.summary = operationTitles[id] ?? operation.summary;
    operation.description = operationDescriptions[id] ?? operation.description;
    operation.tags = operationTags[id] ? [operationTags[id]] : operation.tags;
  }
  if (path.startsWith('/api/v1/me')) {
    operation.security = [{ customerAccessToken: [] }];
    operation['x-scalar-stability'] = 'stable';
    mergeResponse(
      operation,
      '401',
      'Missing or invalid customer authentication.',
    );
    mergeResponse(operation, '403', 'Insufficient scope, realm or CSRF token.');
    if (['delete', 'patch', 'post', 'put'].includes(method)) {
      mergeResponse(
        operation,
        '400',
        'Invalid request body, header or parameter.',
      );
      mergeResponse(
        operation,
        '409',
        'Version, idempotency or business conflict.',
      );
    }
  }
  if (path.startsWith('/api/v1/vehicles/')) {
    operation.security = [];
    operation['x-scalar-stability'] = 'stable';
    mergeResponse(operation, '400', 'Unsupported market or invalid request.');
    mergeResponse(operation, '404', 'Vehicle model not found.');
    mergeResponse(
      operation,
      '503',
      'No approved fresh catalog release is available.',
    );
  }
  if (path.startsWith('/api/v1/chat/')) {
    operation['x-scalar-stability'] = 'experimental';
    operation['x-badges'] = [{ name: 'AI gated', color: '#7c3aed' }];
    mergeResponse(
      operation,
      '401',
      'Missing or invalid authenticated customer token.',
    );
    mergeResponse(
      operation,
      '403',
      'Invalid anonymous capability or subject access.',
    );
    mergeResponse(
      operation,
      '503',
      'AI runtime or release manifest is unavailable.',
    );
  }
}

function polishOpenApiDocument(
  document: MutableOpenApiDocument,
): OpenAPIObject {
  document.info.description = [
    'Production-minded API reference for VFBiz account, customer and vehicle foundations.',
    '',
    '- Browser OIDC and opaque sessions belong to Customer Portal BFF; this resource API accepts Bearer tokens only.',
    '- Customer resources are subject-scoped and fail closed on missing identity, scope or freshness.',
    '- Mutations use optimistic concurrency, idempotency and RFC Problem Details.',
  ].join('\n');
  document.info['x-scalar-links'] = [
    { name: 'Security model', url: '/docs/security-data-ai' },
    { name: 'OpenAPI JSON', url: `/${openApiJsonPath}` },
    { name: 'Workforce API', url: '/reference/workforce' },
  ];
  document.info['x-scalar-sdk-installation'] = [
    {
      description:
        'The generated TypeScript SDK is produced from the reviewed OpenAPI contract.\n\n```sh\nnpm run sdk:generate\n```',
      lang: 'TypeScript',
    },
  ];
  document.servers = [
    { description: 'Local development', url: 'http://127.0.0.1:8000' },
    { description: 'Staging', url: 'https://staging-api.vfbiz.example' },
  ];
  document.tags = [
    {
      description: 'Subject-scoped customer profile, consent and privacy APIs.',
      name: 'Customer',
      'x-displayName': '\u00A0\u00A01.1 Customer',
    },
    {
      description: 'Customer garage and self-reported vehicle references.',
      name: 'Garage',
      'x-displayName': '\u00A0\u00A01.2 Garage',
    },
    {
      description: 'Approved vehicle catalog projections.',
      name: 'Vehicle Catalog',
      'x-displayName': '\u00A0\u00A02.1 Vehicles',
    },
    {
      description: 'Health and operational diagnostics.',
      name: 'health',
      'x-displayName': '\u00A0\u00A03.1 System',
    },
  ];
  document['x-tagGroups'] = [
    {
      name: '1. Customer Experience',
      tags: ['Customer', 'Garage'],
    },
    { name: '2. Product Data', tags: ['Vehicle Catalog'] },
    { name: '3. Platform', tags: ['health'] },
  ];
  for (const entry of operationEntries(document)) polishOperation(entry);
  return document as unknown as OpenAPIObject;
}

export function createOpenApiDocument(
  application: NestFastifyApplication,
): OpenAPIObject {
  const configuration = new DocumentBuilder()
    .setTitle('VFBiz Customer API')
    .setDescription('Customer-grade account, garage and vehicle APIs.')
    .setVersion('1.0.0')
    .addBearerAuth(
      {
        type: 'http',
        scheme: 'bearer',
        bearerFormat: 'JWT',
        description: 'OIDC access token issued for the vfbiz-api audience.',
      },
      'customerAccessToken',
    )
    .build();
  return polishOpenApiDocument(
    SwaggerModule.createDocument(application, configuration, {
      operationIdFactory: (_controllerKey, methodKey) => methodKey,
    }) as unknown as MutableOpenApiDocument,
  );
}

export function configureOpenApi(application: NestFastifyApplication): void {
  const document = createOpenApiDocument(application);
  const fastify = application.getHttpAdapter().getInstance();
  fastify.get('/reference', (_request, reply) =>
    reply
      .code(308)
      .header('Cache-Control', 'no-store')
      .header('Location', scalarPath)
      .send(),
  );
  fastify.get('/api-docs', (_request, reply) =>
    reply
      .code(308)
      .header('Cache-Control', 'no-store')
      .header('Location', `/${swaggerPath}`)
      .send(),
  );
  fastify.get('/api-docs/openapi.json', (_request, reply) =>
    reply
      .code(308)
      .header('Cache-Control', 'no-store')
      .header('Location', `/${openApiJsonPath}`)
      .send(),
  );
  SwaggerModule.setup(swaggerPath, application, document, {
    customSiteTitle: 'VFBiz API Swagger',
    jsonDocumentUrl: openApiJsonPath,
    swaggerOptions: { persistAuthorization: false },
  });
  application.use(
    scalarPath,
    apiReference({
      agent: { disabled: true },
      darkMode: true,
      defaultHttpClient: { targetKey: 'shell', clientKey: 'curl' },
      defaultOpenAllTags: true,
      defaultOpenFirstTag: true,
      documentDownloadType: 'both',
      expandAllResponses: false,
      expandAllSchemaProperties: false,
      favicon: scalarFavicon,
      hideDarkModeToggle: false,
      layout: 'modern',
      modelsSectionLabel: 'Schemas',
      operationTitleSource: 'summary',
      pageTitle: 'VFBiz Customer API Reference',
      persistAuth: false,
      searchHotKey: 'k',
      showOperationId: false,
      showSidebar: true,
      showDeveloperTools: 'never',
      theme: 'default',
      url: `/${openApiJsonPath}`,
      withFastify: true,
    }),
  );
}
