import { Injectable } from '@nestjs/common';
import { ThrottlerGuard } from '@nestjs/throttler';
import type { FastifyRequest } from 'fastify';

@Injectable()
export class ChatThrottlerGuard extends ThrottlerGuard {
  protected getTracker(req: FastifyRequest): Promise<string> {
    // Fastify derives `ip` from X-Forwarded-For only when the direct peer
    // matches the bootstrap CIDR allowlist. Never consume the raw chain here.
    return Promise.resolve(resolveChatThrottleAddress(req));
  }
}

export function resolveChatThrottleAddress(
  request: Pick<FastifyRequest, 'ip'>,
): string {
  return request.ip;
}
