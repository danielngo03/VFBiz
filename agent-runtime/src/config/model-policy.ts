export type RuntimeRole =
  | "orchestrator"
  | "explorer"
  | "implementer"
  | "reviewer-verifier"
  | "risk-reviewer"
  | "integrator";

export interface ModelPolicy {
  modelFor(role: RuntimeRole): string;
}

export class EnvironmentModelPolicy implements ModelPolicy {
  public constructor(private readonly source = process.env) {}

  public modelFor(role: RuntimeRole): string {
    const roleKey = role.toUpperCase().replaceAll("-", "_");
    return (
      this.source[`VFBIZ_AGENT_RUNTIME_MODEL_${roleKey}`] ??
      this.source.VFBIZ_AGENT_RUNTIME_MODEL ??
      "gpt-5.5"
    );
  }
}
