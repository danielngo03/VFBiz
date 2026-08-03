import { describe, expect, it } from "vitest";
import { OpenAiTraceSink } from "../../src/adapters/observability/openai-trace-sink.js";
import { buildRunnerTraceConfiguration } from "../../src/adapters/openai/agents-sdk-executor.js";
import type { ResolvedRuntimeContext } from "../../src/ports/governance-gateway.js";

describe("trace redaction", () => {
  it("records correlation metadata and drops arbitrary sensitive attributes", () => {
    const records: Record<string, unknown>[] = [];
    const sink = new OpenAiTraceSink(true, (record) => records.push(record));
    sink.record("agent.completed", {
      workItemKey: "VFBIZ-0204",
      runId: "run-fixture",
      role: "orchestrator",
      team: "agent-platform",
      workspace: "agent-runtime",
      contextKey: "a".repeat(64),
      revision: "731ba5f",
    }, {
      status: "completed",
      prompt: "do not leak this",
      secret: "never",
    });
    expect(records).toHaveLength(1);
    expect(JSON.stringify(records)).not.toContain("do not leak this");
    expect(JSON.stringify(records)).not.toContain("never");
  });

  it("uses the redacted settings on the actual Agents SDK Runner path", () => {
    const context = {
      workItemKey: "VFBIZ-0204",
      ownerTeam: "agent-platform",
      workspace: "agent-runtime",
      contextKey: "a".repeat(64),
      baseRevision: "731ba5f",
    } as ResolvedRuntimeContext;
    const configuration = buildRunnerTraceConfiguration({ runId: "run-fixture", context }, true);
    expect(configuration.traceIncludeSensitiveData).toBe(false);
    expect(configuration.tracingDisabled).toBe(false);
    expect(configuration.traceMetadata).toEqual({
      work_item: "VFBIZ-0204",
      run: "run-fixture",
      role: "orchestrator",
      team: "agent-platform",
      workspace: "agent-runtime",
      context_key: "a".repeat(64),
      revision: "731ba5f",
    });
    expect(JSON.stringify(configuration)).not.toContain("objective");
  });
});
