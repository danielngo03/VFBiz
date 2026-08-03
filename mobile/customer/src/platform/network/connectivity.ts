import NetInfo from "@react-native-community/netinfo";
import { useEffect, useState } from "react";
import type { FreshnessState } from "../../domain/freshness/freshness";

export type Connectivity = "online" | "offline" | "unknown";

export function useConnectivity(): Connectivity {
  const [connectivity, setConnectivity] = useState<Connectivity>("unknown");
  useEffect(
    () =>
      NetInfo.addEventListener((state) => {
        if (state.isConnected === false) setConnectivity("offline");
        else if (state.isConnected === true) setConnectivity("online");
        else setConnectivity("unknown");
      }),
    [],
  );
  return connectivity;
}

export function resourceFreshness(input: {
  connectivity: Connectivity;
  hasData: boolean;
  stale: boolean;
  error: boolean;
}): FreshnessState {
  if (input.connectivity === "offline") return "offline";
  if (input.connectivity === "unknown" && !input.hasData) return "unknown";
  if (input.error && !input.hasData) return "restricted";
  if (input.error || input.stale) return "stale";
  return input.hasData ? "fresh" : "unknown";
}
