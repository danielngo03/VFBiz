import { Injectable, OnModuleDestroy } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import Redis from 'ioredis';
import type { EnvironmentVariables } from '../config/env.schema';

@Injectable()
export class RedisConnectionService implements OnModuleDestroy {
  readonly client: Redis;

  constructor(config: ConfigService<EnvironmentVariables, true>) {
    this.client = new Redis(config.getOrThrow('VFBIZ_REDIS_URL'), {
      enableOfflineQueue: false,
      lazyConnect: true,
      maxRetriesPerRequest: 1,
    });
  }

  async ensureConnected(): Promise<void> {
    if (this.client.status === 'wait') {
      await this.client.connect();
    }
  }

  async onModuleDestroy(): Promise<void> {
    if (this.client.status === 'wait' || this.client.status === 'end') return;
    try {
      await this.client.quit();
    } catch {
      this.client.disconnect(false);
    }
  }
}
