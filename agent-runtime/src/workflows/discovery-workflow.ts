export const discoveryWorkflow = Object.freeze({
  mode: "discovery" as const,
  stages: ["resolve-context", "explorer", "assemble-decision-packet"] as const,
  writableRoles: [] as const,
  requiredReviewers: [] as const,
});
