import { Controller, Get, ServiceUnavailableException } from '@nestjs/common';
import {
  ApiOkResponse,
  ApiOperation,
  ApiServiceUnavailableResponse,
  ApiTags,
} from '@nestjs/swagger';
import { PrismaService } from '../database/prisma.service';
import { Public } from '../http/public.decorator';

@ApiTags('health')
@Controller({ path: 'health', version: '1' })
export class HealthController {
  constructor(private readonly prisma: PrismaService) {}

  @Public()
  @Get('live')
  @ApiOperation({
    operationId: 'liveness',
    summary: 'Check liveness',
    description: 'Returns ok when the API process is serving requests.',
  })
  @ApiOkResponse({
    schema: {
      type: 'object',
      properties: { status: { type: 'string', enum: ['ok'] } },
    },
  })
  liveness(): Readonly<{ status: 'ok' }> {
    return Object.freeze({ status: 'ok' });
  }

  @Public()
  @Get('ready')
  @ApiOperation({
    operationId: 'readiness',
    summary: 'Check readiness',
    description:
      'Returns ready only when the API can execute a lightweight PostgreSQL probe.',
  })
  @ApiOkResponse({
    schema: {
      type: 'object',
      properties: {
        status: { type: 'string', enum: ['ready'] },
        dependencies: {
          type: 'object',
          properties: {
            database: { type: 'string', enum: ['up'] },
          },
          required: ['database'],
        },
      },
      required: ['status', 'dependencies'],
    },
  })
  @ApiServiceUnavailableResponse({
    description: 'PostgreSQL is unavailable.',
  })
  async readiness(): Promise<
    Readonly<{ status: 'ready'; dependencies: { database: 'up' } }>
  > {
    try {
      await this.prisma.$queryRaw`SELECT 1`;
    } catch {
      throw new ServiceUnavailableException({
        code: 'DATABASE_NOT_READY',
        message: 'The API database dependency is unavailable.',
      });
    }

    return Object.freeze({
      status: 'ready',
      dependencies: Object.freeze({ database: 'up' }),
    });
  }
}
