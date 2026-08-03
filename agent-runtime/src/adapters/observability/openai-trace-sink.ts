import type { TraceMetadata, TraceSink } from "../../ports/trace-sink.js";

const safeAttributePattern = /^(?:attempt|cycle|event_count|status|mode)$/;

export class OpenAiTraceSink implements TraceSink {
  public constructor(
    private readonly enabled: boolean,
    private readonly receiver: (record: Record<string, unknown>) => void = () => undefined,
  ) {}

  public record(
    name: string,
    metadata: TraceMetadata,
    safeAttributes: Record<string, string | number | boolean> = {},
  ): void {
    if (!this.enabled) return;
    const attributes = Object.fromEntries(
      Object.entries(safeAttributes).filter(([key]) => safeAttributePattern.test(key)),
    );
    this.receiver({ name, metadata: { ...metadata }, attributes });
  }
}
