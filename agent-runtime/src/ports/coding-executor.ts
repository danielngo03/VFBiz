export interface CodingExecutionRequest {
  runId: string;
  operationId: string;
  objective: string;
  repositoryPath: string;
  allowedPaths: string[];
  mode: "read-only" | "workspace-write";
}

export interface CodingExecutionResult {
  summary: string;
  changedPaths: string[];
  evidence: string[];
}

export interface CodingExecutor {
  execute(request: CodingExecutionRequest): Promise<CodingExecutionResult>;
}
