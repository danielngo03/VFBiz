import { Controller, Get } from '@nestjs/common';
import { Test, TestingModule } from '@nestjs/testing';
import {
  FastifyAdapter,
  NestFastifyApplication,
} from '@nestjs/platform-fastify';
import { AppModule } from '../../../src/app.module';
import { configureApplication } from '../../../src/bootstrap/configure-application';

@Controller({ path: 'security-test', version: '1' })
class ProtectedTestController {
  @Get()
  protectedRoute(): { status: string } {
    return { status: 'should-not-be-reached' };
  }
}

describe('protected-by-default security boundary (e2e)', () => {
  let app: NestFastifyApplication;

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
      controllers: [ProtectedTestController],
    }).compile();

    app = moduleFixture.createNestApplication<NestFastifyApplication>(
      new FastifyAdapter(),
    );
    await configureApplication(app);
    await app.init();
    await app.getHttpAdapter().getInstance().ready();
  });

  it('denies a protected route when authentication is missing', async () => {
    const response = await app.inject({
      method: 'GET',
      url: '/api/v1/security-test',
    });
    expect(response.statusCode).toBe(401);
    expect(response.json()).toMatchObject({ code: 'AUTHENTICATION_REQUIRED' });
  });

  it('denies malformed bearer tokens without contacting a provider', async () => {
    const response = await app.inject({
      headers: { authorization: 'Bearer not-a-jwt' },
      method: 'GET',
      url: '/api/v1/security-test',
    });
    expect(response.statusCode).toBe(401);
    expect(response.json()).toMatchObject({ code: 'INVALID_ACCESS_TOKEN' });
  });

  it('keeps explicitly public liveness available', async () => {
    const response = await app.inject({
      method: 'GET',
      url: '/api/v1/health/live',
    });
    expect(response.statusCode).toBe(200);
  });

  afterAll(async () => app.close());
});
