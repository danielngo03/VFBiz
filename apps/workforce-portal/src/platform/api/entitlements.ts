import {z} from 'zod';

const capabilityKeySchema = z.string().trim().min(3).regex(
  /^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*){2,}$/,
  'Capability phải theo namespace resource action.',
);

export const workforceEntitlementsSchema = z.object({
  identitySubjectId: z.string().uuid(),
  revision: z.string().min(1),
  capabilities: z.array(
    z.object({
      key: capabilityKeySchema,
      riskTier: z.enum(['standard', 'sensitive', 'privileged']),
      scopes: z.array(
        z.object({
          type: z.enum(['global', 'market', 'showroom', 'department']),
          ref: z.string().min(1),
        }).strict(),
      ),
    }).strict(),
  ),
}).strict();

export type WorkforceEntitlements = z.infer<typeof workforceEntitlementsSchema>;

export function hasAllCapabilities(
  entitlements: WorkforceEntitlements,
  required: readonly string[],
): boolean {
  const granted = new Set(entitlements.capabilities.map(({key}) => key));
  return required.every((capability) => granted.has(capability));
}
