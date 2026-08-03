export interface TraceMetadata {
  workItemKey: string;
  runId: string;
  role: string;
  team: string;
  workspace: string;
  contextKey: string;
  revision: string;
}

export interface TraceSink {
  record(name: string, metadata: TraceMetadata, safeAttributes?: Record<string, string | number | boolean>): void;
}
