export const boundedWorkflow = Object.freeze({
  mode: "bounded" as const,
  stages: ["resolve-context", "explorer", "implementer", "reviewer-verifier", "assemble-evidence"] as const,
  writableRoles: ["implementer"] as const,
  requiredReviewers: ["reviewer-verifier"] as const,
});
