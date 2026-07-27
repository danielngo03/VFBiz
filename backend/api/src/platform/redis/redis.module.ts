import { Global, Module } from '@nestjs/common';
import { RedisConnectionService } from './redis-connection.service';
import { RedisThrottlerStorageService } from './redis-throttler-storage.service';

@Global()
@Module({
  exports: [RedisConnectionService, RedisThrottlerStorageService],
  providers: [RedisConnectionService, RedisThrottlerStorageService],
})
export class RedisModule {}
