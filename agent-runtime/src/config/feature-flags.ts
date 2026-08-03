export interface RuntimeFeatureFlags {
  liveProvider: boolean;
  liveCodex: boolean;
  externalMutation: false;
  productWorkspaceWrite: false;
  nestedDelegation: false;
  multiMachine: false;
}

function enabled(value: string | undefined): boolean {
  return value === "true" || value === "1";
}

export function featureFlags(source = process.env): RuntimeFeatureFlags {
  return Object.freeze({
    liveProvider: enabled(
      source.VFBIZ_AGENT_RUNTIME_LIVE_ENABLED ?? source.VFBIZ_AGENT_RUNTIME_OPENAI_ENABLED,
    ),
    liveCodex: enabled(source.VFBIZ_AGENT_RUNTIME_CODEX_ENABLED),
    externalMutation: false,
    productWorkspaceWrite: false,
    nestedDelegation: false,
    multiMachine: false,
  });
}
