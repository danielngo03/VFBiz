import { describe, expect, it } from "vitest";
import { assertProgramPathAllowed, assertToolAllowed } from "../../src/config/tool-policy.js";

describe("prompt injection evaluation", () => {
  it("does not let task text expand tools or product paths", () => {
    const injectedTool = "deploy-production";
    const injectedPath = "mobile/customer/src/auth.ts";
    expect(() => assertToolAllowed(injectedTool)).toThrow();
    expect(() => assertProgramPathAllowed(injectedPath)).toThrow();
  });
});
