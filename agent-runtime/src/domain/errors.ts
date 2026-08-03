export class RuntimeError extends Error {
  public constructor(
    public readonly code: string,
    message: string,
    public readonly retryable = false,
  ) {
    super(message);
    this.name = "RuntimeError";
  }
}

export class OptimisticConflictError extends RuntimeError {
  public constructor(runId: string) {
    super("OPTIMISTIC_CONFLICT", `runtime run changed concurrently: ${runId}`, true);
  }
}

export class BoundaryViolationError extends RuntimeError {
  public constructor(message: string) {
    super("BOUNDARY_VIOLATION", message, false);
  }
}
