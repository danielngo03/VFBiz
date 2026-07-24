import {z} from 'zod';

const uuidSchema = z.string().uuid();
const dateTimeSchema = z.string().datetime({offset: true});
const nullableDateTimeSchema = dateTimeSchema.nullable().optional();

export const authorizationScopeSchema = z.object({
  type: z.enum(['global', 'market', 'showroom', 'department']),
  ref: z.string().min(1),
});

export const workforceRoleSchema = z.object({
  id: uuidSchema,
  key: z.string().min(1),
  displayName: z.string().min(1),
  description: z.string().nullable().optional(),
  status: z.enum(['active', 'disabled']),
  system: z.boolean(),
  version: z.number().int().positive(),
  capabilityKeys: z.array(z.string().min(1)),
  createdAt: dateTimeSchema,
  updatedAt: dateTimeSchema,
});

export const workforceAssignmentSchema = z.object({
  id: uuidSchema,
  identitySubjectId: uuidSchema,
  roleId: uuidSchema,
  roleKey: z.string().min(1),
  status: z.enum(['active', 'revoked']),
  effectiveAt: dateTimeSchema,
  expiresAt: nullableDateTimeSchema,
  reason: z.string().min(1),
  version: z.number().int().positive(),
  scopes: z.array(authorizationScopeSchema),
});

export const authorizationChangeRequestSchema = z.object({
  id: uuidSchema,
  requestType: z.string().min(1),
  status: z.enum(['pending', 'approved', 'rejected']),
  riskTier: z.enum(['standard', 'sensitive', 'privileged']),
  requesterRef: z.string().min(1),
  targetType: z.string().min(1),
  targetRef: z.string().min(1),
  reason: z.string().min(1),
  payload: z.unknown(),
  expiresAt: dateTimeSchema,
  decidedAt: nullableDateTimeSchema,
});

export const workforceAuditEventSchema = z.object({
  id: uuidSchema,
  actorRef: z.string().nullable().optional(),
  action: z.string().min(1),
  resourceType: z.string().min(1),
  resourceId: z.string().nullable().optional(),
  outcome: z.string().min(1),
  correlationId: uuidSchema,
  occurredAt: dateTimeSchema,
});

export type WorkforceRole = z.infer<typeof workforceRoleSchema>;
export type WorkforceAssignment = z.infer<typeof workforceAssignmentSchema>;
export type AuthorizationChangeRequest = z.infer<
  typeof authorizationChangeRequestSchema
>;
export type WorkforceAuditEvent = z.infer<typeof workforceAuditEventSchema>;

export function formatWorkforceDateTime(value: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Ho_Chi_Minh',
  }).format(new Date(value));
}

export function formatAuthorizationScope(
  scope: z.infer<typeof authorizationScopeSchema>,
): string {
  if (scope.type === 'global') return 'Toàn hệ thống';
  const labels = {
    market: 'Thị trường',
    showroom: 'Showroom',
    department: 'Phòng ban',
  } as const;
  return `${labels[scope.type]}: ${scope.ref}`;
}
