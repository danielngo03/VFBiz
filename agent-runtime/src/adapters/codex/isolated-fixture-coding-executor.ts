import type {
  CodingExecutionRequest,
  CodingExecutionResult,
  CodingExecutor,
} from "../../ports/coding-executor.js";
import type { WorkspaceExecutor } from "../../ports/workspace-executor.js";

export class IsolatedFixtureCodingExecutor implements CodingExecutor {
  public constructor(
    private readonly sourceFixture: string,
    private readonly workspaces: WorkspaceExecutor,
    private readonly delegate: CodingExecutor,
  ) {}

  public async execute(request: CodingExecutionRequest): Promise<CodingExecutionResult> {
    const workspace = await this.workspaces.createFixtureWorktree(
      this.sourceFixture,
      `${request.runId}-${request.operationId}`,
    );
    try {
      return await this.delegate.execute({ ...request, repositoryPath: workspace.root });
    } finally {
      await workspace.dispose();
    }
  }
}
