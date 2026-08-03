import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { CliGovernanceGateway } from "../../src/adapters/governance/cli-governance-gateway.js";
import type { ResolvedRuntimeContext } from "../../src/ports/governance-gateway.js";

describe("artifact provenance", () => {
  it("recomputes artifact bytes inside the canonical allowed paths", async () => {
    const repositoryRoot = path.resolve(import.meta.dirname, "../../..");
    const artifactPath = "agent-runtime/tests/fixtures/sample-repository/README.md";
    const bytes = await readFile(path.join(repositoryRoot, artifactPath));
    const sha256 = createHash("sha256").update(bytes).digest("hex");
    const gateway = new CliGovernanceGateway(repositoryRoot);
    const context = {
      allowedPaths: ["agent-runtime"],
    } as ResolvedRuntimeContext;
    await expect(gateway.verifyArtifact(context, { path: artifactPath, sha256 })).resolves.toBeUndefined();
    await expect(gateway.verifyArtifact(context, { path: artifactPath, sha256: "0".repeat(64) }))
      .rejects.toMatchObject({ code: "ARTIFACT_DIGEST_MISMATCH" });
  });
});
