import { ConfigService } from '@nestjs/config';
import { PrismaService } from './prisma.service';

describe('PrismaService connection lifecycle', () => {
  it('does not connect during test/OpenAPI assembly', async () => {
    const config = {
      getOrThrow: jest.fn((key: string) => {
        if (key === 'NODE_ENV') return 'test';
        return 'postgresql://test:test@127.0.0.1:5432/test';
      }),
    } as unknown as ConfigService;
    const service = new PrismaService(config);
    const connect = jest.spyOn(service, '$connect');

    await service.onModuleInit();

    expect(connect).not.toHaveBeenCalled();
  });

  it('connects eagerly outside the test runtime', async () => {
    const config = {
      getOrThrow: jest.fn((key: string) => {
        if (key === 'NODE_ENV') return 'staging';
        return 'postgresql://test:test@127.0.0.1:5432/test';
      }),
    } as unknown as ConfigService;
    const service = new PrismaService(config);
    const connect = jest.spyOn(service, '$connect').mockResolvedValue();

    await service.onModuleInit();

    expect(connect).toHaveBeenCalledTimes(1);
  });
});
