import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import type {
  AuthorizationChangeRequestView,
  AuthorizationScope,
  CapabilityDefinition,
  WorkforceAssignmentView,
  WorkforceAuditEventView,
  WorkforceDirectorySubjectView,
  WorkforceEntitlements,
  WorkforceOrganizationUnitView,
  WorkforceRoleView,
} from '../../domain/workforce-authorization';

export interface CreateWorkforceRoleCommand {
  readonly key: string;
  readonly displayName: string;
  readonly description?: string;
  readonly actorRef: string;
  readonly correlationId: string;
}

export interface UpdateWorkforceRoleCommand {
  readonly roleId: string;
  readonly expectedVersion: number;
  readonly displayName?: string;
  readonly description?: string | null;
  readonly actorRef: string;
  readonly correlationId: string;
}

export interface ReplaceRoleCapabilitiesCommand {
  readonly roleId: string;
  readonly expectedVersion: number;
  readonly capabilityKeys: readonly string[];
  readonly actorRef: string;
  readonly correlationId: string;
}

export interface CreateAssignmentCommand {
  readonly identitySubjectId: string;
  readonly roleId: string;
  readonly effectiveAt: Date;
  readonly expiresAt: Date | null;
  readonly reason: string;
  readonly scopes: readonly AuthorizationScope[];
  readonly actorRef: string;
  readonly correlationId: string;
}

export interface CreateChangeRequestCommand {
  readonly requestType: string;
  readonly riskTier: 'standard' | 'sensitive' | 'privileged';
  readonly requesterRef: string;
  readonly targetType: string;
  readonly targetRef: string;
  readonly reason: string;
  readonly payload: unknown;
  readonly correlationId: string;
  readonly expiresAt: Date;
}

export abstract class WorkforceAuthorizationRepository {
  abstract resolveEntitlements(
    principal: AccessPrincipal,
    now: Date,
  ): Promise<WorkforceEntitlements | null>;

  abstract listCapabilities(): Promise<readonly CapabilityDefinition[]>;
  abstract listRoles(): Promise<readonly WorkforceRoleView[]>;
  abstract getRole(roleId: string): Promise<WorkforceRoleView | null>;
  abstract isRoleAssignedToPrincipal(
    roleId: string,
    principal: AccessPrincipal,
    now: Date,
  ): Promise<boolean>;
  abstract createRole(
    command: CreateWorkforceRoleCommand,
  ): Promise<WorkforceRoleView>;
  abstract updateRole(
    command: UpdateWorkforceRoleCommand,
  ): Promise<WorkforceRoleView>;
  abstract replaceRoleCapabilities(
    command: ReplaceRoleCapabilitiesCommand,
  ): Promise<WorkforceRoleView>;
  abstract disableRole(
    roleId: string,
    expectedVersion: number,
    actorRef: string,
    correlationId: string,
  ): Promise<WorkforceRoleView>;

  abstract listAssignments(): Promise<readonly WorkforceAssignmentView[]>;
  abstract createAssignment(
    command: CreateAssignmentCommand,
  ): Promise<WorkforceAssignmentView>;
  abstract revokeAssignment(
    assignmentId: string,
    expectedVersion: number,
    actorRef: string,
    correlationId: string,
  ): Promise<WorkforceAssignmentView>;

  abstract listChangeRequests(): Promise<
    readonly AuthorizationChangeRequestView[]
  >;
  abstract createChangeRequest(
    command: CreateChangeRequestCommand,
  ): Promise<AuthorizationChangeRequestView>;
  abstract decideChangeRequest(
    requestId: string,
    decision: 'approved' | 'rejected',
    approverRef: string,
    evidenceRef: string,
    reason: string | null,
    correlationId: string,
    now: Date,
  ): Promise<AuthorizationChangeRequestView>;

  abstract listDirectorySubjects(): Promise<
    readonly WorkforceDirectorySubjectView[]
  >;
  abstract listOrganizationUnits(): Promise<
    readonly WorkforceOrganizationUnitView[]
  >;
  abstract listAuditEvents(): Promise<readonly WorkforceAuditEventView[]>;
}
