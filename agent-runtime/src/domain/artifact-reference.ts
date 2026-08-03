export interface ArtifactReference {
  id: string;
  runId: string;
  kind: "decision-packet" | "worker-report" | "review-finding" | "evidence" | "sandbox-output";
  path: string;
  sha256: string;
  mediaType: string;
  createdAt: string;
}
