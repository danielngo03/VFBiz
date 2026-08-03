export interface RuntimeFeatureFlags {
  liveOpenAi: boolean;
  liveCodex: boolean;
  externalMutation: false;
  productWorkspaceWrite: false;
  nestedDelegation: false;
  multiMachine: false;
}

export function featureFlags(source = process.env): RuntimeFeatureFlags {
  return Object.freeze({
    liveOpenAi: source.VFBIZ_AGENT_RUNTIME_OPENAI_ENABLED === "true",
    liveCodex: source.VFBIZ_AGENT_RUNTIME_CODEX_ENABLED === "true",
    externalMutation: false,
    productWorkspaceWrite: false,
    nestedDelegation: false,
    multiMachine: false,
  });
}
