import {
  createParamDecorator,
  ExecutionContext,
  UnauthorizedException,
} from '@nestjs/common';
import type { FastifyRequest } from 'fastify';
import type { AccessPrincipal } from './access-principal';

export const CurrentPrincipal = createParamDecorator(
  (_data: unknown, context: ExecutionContext): AccessPrincipal => {
    const request = context
      .switchToHttp()
      .getRequest<FastifyRequest & { vfbizPrincipal?: AccessPrincipal }>();
    if (request.vfbizPrincipal === undefined) {
      throw new UnauthorizedException({
        code: 'AUTHENTICATION_REQUIRED',
        message: 'A verified access principal is required.',
      });
    }
    return request.vfbizPrincipal;
  },
);
