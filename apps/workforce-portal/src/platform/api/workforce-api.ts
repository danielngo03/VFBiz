import 'server-only';
import type {components} from '@vfbiz/workforce-api-client';
import {z} from 'zod';
import {
  workforceEntitlementsSchema,
  type WorkforceEntitlements,
} from '@/platform/api/entitlements';
import {
  authorizationChangeRequestSchema,
  type AuthorizationChangeRequest,
  workforceAssignmentSchema,
  type WorkforceAssignment,
  workforceAuditEventSchema,
  type WorkforceAuditEvent,
  workforceRoleSchema,
  type WorkforceRole,
} from '@/platform/api/workforce-resources';

export interface WorkforceApiRequest {
  readonly accessToken: string;
  readonly correlationId: string;
}

type GeneratedSchema<Name extends keyof components['schemas']> =
  components['schemas'][Name];

export class WorkforceApiClient {
  constructor(private readonly baseUrl: URL) {}

  async getEntitlements(
    request: WorkforceApiRequest,
  ): Promise<GeneratedSchema<'WorkforceEntitlements'> & WorkforceEntitlements> {
    return this.get(
      '/api/v1/workforce/me/entitlements',
      request,
      workforceEntitlementsSchema,
    );
  }

  async listRoles(
    request: WorkforceApiRequest,
  ): Promise<readonly (GeneratedSchema<'WorkforceRole'> & WorkforceRole)[]> {
    return this.get(
      '/api/v1/workforce/authorization/roles',
      request,
      z.array(workforceRoleSchema),
    );
  }

  async listAssignments(
    request: WorkforceApiRequest,
  ): Promise<
    readonly (GeneratedSchema<'WorkforceAssignment'> & WorkforceAssignment)[]
  > {
    return this.get(
      '/api/v1/workforce/authorization/assignments',
      request,
      z.array(workforceAssignmentSchema),
    );
  }

  async listChangeRequests(
    request: WorkforceApiRequest,
  ): Promise<
    readonly (
      GeneratedSchema<'AuthorizationChangeRequest'> &
      AuthorizationChangeRequest
    )[]
  > {
    return this.get(
      '/api/v1/workforce/authorization/change-requests',
      request,
      z.array(authorizationChangeRequestSchema),
    );
  }

  async listAuditEvents(
    request: WorkforceApiRequest,
  ): Promise<
    readonly (GeneratedSchema<'WorkforceAuditEvent'> & WorkforceAuditEvent)[]
  > {
    return this.get(
      '/api/v1/workforce/audit-events',
      request,
      z.array(workforceAuditEventSchema),
    );
  }

  private async get<T>(
    path: string,
    request: WorkforceApiRequest,
    schema: z.ZodType<T>,
  ): Promise<T> {
    const response = await fetch(new URL(path, this.baseUrl), {
      cache: 'no-store',
      headers: {
        accept: 'application/json',
        authorization: `Bearer ${request.accessToken}`,
        'x-correlation-id': request.correlationId,
      },
      method: 'GET',
    });

    if (!response.ok) {
      throw new WorkforceApiError(
        response.status,
        response.headers.get('x-correlation-id') ?? undefined,
      );
    }

    const payload: unknown = await response.json();
    return schema.parse(payload);
  }
}

export class WorkforceApiError extends Error {
  constructor(
    readonly status: number,
    readonly correlationId?: string,
  ) {
    super('Workforce API request failed.');
    this.name = 'WorkforceApiError';
  }
}
