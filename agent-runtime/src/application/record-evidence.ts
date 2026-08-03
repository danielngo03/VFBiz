import { assertProgramPathAllowed } from "../config/tool-policy.js";
import type { AgentResult } from "../agents/agent-result.js";
import type { RunStore } from "../ports/run-store.js";
import type { GovernanceGateway, ResolvedRuntimeContext } from "../ports/governance-gateway.js";

export async function recordEvidence(
  runId: string,
  result: AgentResult,
  store: RunStore,
  governance: GovernanceGateway,
  context: ResolvedRuntimeContext,
): Promise<void> {
  for (const artifact of result.artifacts) {
    assertProgramPathAllowed(artifact.path);
    await governance.verifyArtifact(context, artifact);
    store.recordArtifact({
      runId,
      kind: artifact.kind,
      path: artifact.path,
      sha256: artifact.sha256,
      mediaType: artifact.mediaType,
    });
  }
}
