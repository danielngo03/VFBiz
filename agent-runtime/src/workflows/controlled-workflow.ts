export const controlledWorkflow = Object.freeze({
  mode: "controlled" as const,
  stages: [
    "resolve-context",
    "explorer",
    "approval-boundary",
    "implementer",
    "reviewer-verifier",
    "risk-reviewer",
    "assemble-evidence",
  ] as const,
  writableRoles: ["implementer"] as const,
  requiredReviewers: ["reviewer-verifier", "risk-reviewer"] as const,
});
