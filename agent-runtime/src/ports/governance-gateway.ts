export interface ResolvedRuntimeContext {
  contextKey: string;
  workItemKey: string;
  workItemRevision: number;
  workspace: string;
  ownerTeam: string;
  ownerDepartment: string;
  accountableRole: string;
  mode: "discovery" | "bounded" | "controlled";
  allowedPaths: string[];
  requiredAuthorities: string[];
  requiredReviewers: string[];
  registeredTeams: string[];
  registeredAuthorities: string[];
  claimRequired: boolean;
  baseRevision: string;
}

export interface ExecutionAuthority {
  claimId: string;
  fencingToken: number;
}

export interface GovernanceGateway {
  resolve(workItemKey: string, targetPath: string): Promise<ResolvedRuntimeContext>;
  assertFresh(context: ResolvedRuntimeContext): Promise<void>;
  assertExecutionAuthority(
    context: ResolvedRuntimeContext,
    authority: ExecutionAuthority | null,
  ): Promise<void>;
  verifyArtifact(
    context: ResolvedRuntimeContext,
    artifact: { path: string; sha256: string },
  ): Promise<void>;
}
