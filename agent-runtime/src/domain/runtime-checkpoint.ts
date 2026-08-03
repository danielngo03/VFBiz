export interface RuntimeCheckpoint {
  id: string;
  runId: string;
  sequence: number;
  kind: "workflow" | "agent-state";
  encryptedState: string;
  stateDigest: string;
  createdAt: string;
}
