import { randomUUID } from 'node:crypto';
import type { FastifyRequest } from 'fastify';

const CORRELATION_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export interface RequestWithContext extends FastifyRequest {
  vfbizCorrelationId?: string;
}

export function resolveCorrelationId(request: FastifyRequest): string {
  const candidate = request.headers['x-correlation-id'];
  if (typeof candidate === 'string' && CORRELATION_ID_PATTERN.test(candidate)) {
    return candidate.toLowerCase();
  }
  return randomUUID();
}

export function requestCorrelationId(request: RequestWithContext): string {
  return request.vfbizCorrelationId ?? randomUUID();
}
