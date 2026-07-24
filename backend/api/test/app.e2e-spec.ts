import { Test, TestingModule } from '@nestjs/testing';
import {
  FastifyAdapter,
  NestFastifyApplication,
} from '@nestjs/platform-fastify';
import { AppModule } from './../src/app.module';
import { configureApplication } from './../src/bootstrap/configure-application';
import { PrismaService } from './../src/platform/database/prisma.service';

describe('AppController (e2e)', () => {
  let app: NestFastifyApplication;
  const databaseProbe = jest.fn();

  beforeEach(async () => {
    databaseProbe.mockReset();
    databaseProbe.mockResolvedValue([{ '?column?': 1 }]);
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    })
      .overrideProvider(PrismaService)
      .useValue({
        $connect: jest.fn(),
        $disconnect: jest.fn(),
        $queryRaw: databaseProbe,
      })
      .compile();

    app = moduleFixture.createNestApplication<NestFastifyApplication>(
      new FastifyAdapter(),
    );
    await configureApplication(app);
    await app.init();
    await app.getHttpAdapter().getInstance().ready();
  });

  it('/api/v1/health/live (GET)', async () => {
    const response = await app.inject({
      method: 'GET',
      url: '/api/v1/health/live',
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({ status: 'ok' });
    expect(response.headers['x-correlation-id']).toMatch(/^[a-f0-9-]{36}$/);
  });

  it('/api/v1/health/ready (GET)', async () => {
    const response = await app.inject({
      method: 'GET',
      url: '/api/v1/health/ready',
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({
      status: 'ready',
      dependencies: { database: 'up' },
    });
    expect(databaseProbe).toHaveBeenCalledTimes(1);
  });

  it('fails readiness without leaking the database error', async () => {
    databaseProbe.mockRejectedValueOnce(
      new Error('postgresql://secret@internal.example/vfbiz'),
    );

    const response = await app.inject({
      method: 'GET',
      url: '/api/v1/health/ready',
    });

    expect(response.statusCode).toBe(503);
    expect(response.json()).toMatchObject({
      status: 503,
      code: 'DATABASE_NOT_READY',
    });
    expect(response.body).not.toContain('secret');
    expect(response.body).not.toContain('internal.example');
  });

  it('returns RFC Problem Details and a correlation ID for unknown routes', async () => {
    const response = await app.inject({
      headers: { 'x-correlation-id': '0d713af6-92f0-40d8-9f57-0ebae8a3e688' },
      method: 'GET',
      url: '/api/v1/not-a-route',
    });

    expect(response.statusCode).toBe(404);
    expect(response.headers['content-type']).toContain(
      'application/problem+json',
    );
    expect(response.headers['x-correlation-id']).toBe(
      '0d713af6-92f0-40d8-9f57-0ebae8a3e688',
    );
    expect(response.json()).toMatchObject({
      type: 'https://vfbiz.vn/problems/not-found',
      title: 'Not Found',
      status: 404,
      code: 'NOT_FOUND',
      correlationId: '0d713af6-92f0-40d8-9f57-0ebae8a3e688',
    });
  });

  it('does not expose the versioned API at an unversioned path', async () => {
    const response = await app.inject({
      method: 'GET',
      url: '/api/health/live',
    });

    expect(response.statusCode).toBe(404);
  });

  afterEach(async () => {
    await app.close();
  });
});
