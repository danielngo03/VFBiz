import type { AccessPrincipal } from './access-principal';

export interface WorkforceEntitlementSnapshot {
  readonly identitySubjectId: string;
  readonly revision: string;
  readonly capabilities: readonly {
    readonly key: string;
    readonly riskTier: 'standard' | 'sensitive' | 'privileged';
    readonly scopes: readonly {
      readonly type: 'global' | 'market' | 'showroom' | 'department';
      readonly ref: string;
    }[];
  }[];
}

export abstract class WorkforceEntitlementReader {
  abstract getEntitlements(
    principal: AccessPrincipal,
    now?: Date,
  ): Promise<WorkforceEntitlementSnapshot | null>;
}
