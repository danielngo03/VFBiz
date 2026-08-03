import * as Application from "expo-application";
import Constants from "expo-constants";
import { runtimeConfig } from "../config/runtime-config";

export function releaseDiagnostics() {
  return {
    environment: runtimeConfig.environment,
    applicationId: Application.applicationId,
    version: Application.nativeApplicationVersion,
    build: Application.nativeBuildVersion,
    runtimeVersion: Constants.expoConfig?.runtimeVersion ?? null,
  } as const;
}
