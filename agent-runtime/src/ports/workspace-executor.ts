export interface FixtureWorkspace {
  root: string;
  branch: string;
  baseRevision: string;
  dispose(): Promise<void>;
}

export interface WorkspaceExecutor {
  createFixtureWorktree(sourceFixture: string, runId: string): Promise<FixtureWorkspace>;
  assertFixtureWorkspace(workspaceRoot: string): Promise<void>;
  assertPathsInside(workspaceRoot: string, paths: string[]): Promise<void>;
}
