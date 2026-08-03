export interface ParsedSseEvent {
  readonly id?: string;
  readonly event?: string;
  readonly data: string;
}

export class SseParser {
  private buffer = "";

  push(chunk: string): ParsedSseEvent[] {
    this.buffer += chunk;
    this.buffer = this.buffer.replaceAll("\r\n", "\n");
    const frames = this.buffer.split("\n\n");
    this.buffer = frames.pop() ?? "";
    return frames.flatMap(parseFrame);
  }
}

function parseFrame(frame: string): ParsedSseEvent[] {
  let id: string | undefined;
  let event: string | undefined;
  const data: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith(":")) continue;
    if (line.startsWith("id:")) id = line.slice(3).trimStart();
    if (line.startsWith("event:")) event = line.slice(6).trimStart();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  return data.length === 0
    ? []
    : [{ ...(event ? { event } : {}), ...(id ? { id } : {}), data: data.join("\n") }];
}
