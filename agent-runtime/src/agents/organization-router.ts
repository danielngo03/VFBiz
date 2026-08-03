export interface OrganizationRegistry {
  humanAuthorities: string[];
  workspaces: Array<{ id: string; path: string }>;
  departments: Array<{ id: string; workspaces: string[] }>;
  teams: Array<{ id: string; departmentId: string; workspaces: string[]; paths: string[] }>;
}

export type RoutingDecision =
  | {
      status: "routed";
      teamId: string;
      departmentId: string;
      workspaceId: string;
    }
  | {
      status: "needs-decision";
      code: "UNKNOWN_TEAM" | "WORKSPACE_MISMATCH" | "MISSING_AUTHORITY";
      summary: string;
    };

export function routeRegisteredTask(
  organization: OrganizationRegistry,
  requestedTeam: string,
  workspaceId: string,
  requiredAuthorities: string[] = [],
): RoutingDecision {
  const team = organization.teams.find(({ id }) => id === requestedTeam);
  if (!team) {
    return { status: "needs-decision", code: "UNKNOWN_TEAM", summary: `Unknown registered team: ${requestedTeam}` };
  }
  if (!team.workspaces.includes(workspaceId)) {
    return {
      status: "needs-decision",
      code: "WORKSPACE_MISMATCH",
      summary: `Team ${team.id} does not own workspace ${workspaceId}`,
    };
  }
  const missingAuthority = requiredAuthorities.find(
    (authority) => !organization.humanAuthorities.includes(authority),
  );
  if (missingAuthority) {
    return {
      status: "needs-decision",
      code: "MISSING_AUTHORITY",
      summary: `Unknown required human authority: ${missingAuthority}`,
    };
  }
  const department = organization.departments.find(({ id }) => id === team.departmentId);
  if (!department) {
    return {
      status: "needs-decision",
      code: "WORKSPACE_MISMATCH",
      summary: `Team ${team.id} has no registered department`,
    };
  }
  return {
    status: "routed",
    teamId: team.id,
    departmentId: department.id,
    workspaceId,
  };
}
