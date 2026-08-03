export type ConsentState = "granted" | "withdrawn";

export interface ConsentDecision {
  purpose: string;
  policyVersion: string;
  state: ConsentState;
}
