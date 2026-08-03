import { readFile } from "node:fs/promises";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { routeRegisteredTask, type OrganizationRegistry } from "../../src/agents/organization-router.js";

const repositoryRoot = path.resolve(import.meta.dirname, "../../..");
const organization = JSON.parse(
  await readFile(path.join(repositoryRoot, ".agents/organization.json"), "utf8"),
) as OrganizationRegistry;

describe("enterprise routing evaluation", () => {
  it("routes a synthetic task for every registered team and workspace", () => {
    for (const team of organization.teams) {
      for (const workspace of team.workspaces) {
        expect(routeRegisteredTask(organization, team.id, workspace)).toEqual({
          status: "routed",
          teamId: team.id,
          departmentId: team.departmentId,
          workspaceId: workspace,
        });
      }
    }
  });

  it("returns a typed decision packet for unknown owner or authority", () => {
    expect(routeRegisteredTask(organization, "invented-team", "root")).toMatchObject({
      status: "needs-decision",
      code: "UNKNOWN_TEAM",
    });
    expect(routeRegisteredTask(organization, "agent-platform", "agent-runtime", ["robot-ceo"])).toMatchObject({
      status: "needs-decision",
      code: "MISSING_AUTHORITY",
    });
  });
});
