import { RuntimeError } from "../domain/errors.js";

export type RuntimeProviderKind = "openai" | "openai-compatible";
export type RuntimeProviderApiMode = "responses" | "chat-completions";

export interface RuntimeProviderConfiguration {
  kind: RuntimeProviderKind;
  apiKey: string | null;
  baseUrl: string | null;
  apiMode: RuntimeProviderApiMode;
}

function providerKind(value: string | undefined): RuntimeProviderKind {
  const normalized = value?.trim().toLowerCase() ?? "openai";
  if (normalized === "openai" || normalized === "openai-compatible") return normalized;
  throw new RuntimeError(
    "PROVIDER_KIND_INVALID",
    "VFBIZ_AGENT_RUNTIME_PROVIDER must be openai or openai-compatible",
  );
}

function providerApiMode(
  value: string | undefined,
  kind: RuntimeProviderKind,
): RuntimeProviderApiMode {
  const normalized = value?.trim().toLowerCase();
  if (!normalized) return kind === "openai" ? "responses" : "chat-completions";
  if (normalized === "responses" || normalized === "chat-completions") return normalized;
  throw new RuntimeError(
    "PROVIDER_API_MODE_INVALID",
    "VFBIZ_AGENT_RUNTIME_API_MODE must be responses or chat-completions",
  );
}

function normalizedBaseUrl(value: string | undefined): string | null {
  if (!value?.trim()) return null;
  let url: URL;
  try {
    url = new URL(value.trim());
  } catch {
    throw new RuntimeError("PROVIDER_BASE_URL_INVALID", "provider base URL must be an absolute URL");
  }
  const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (url.protocol !== "https:" && !(url.protocol === "http:" && loopback)) {
    throw new RuntimeError(
      "PROVIDER_BASE_URL_INSECURE",
      "provider base URL must use HTTPS; HTTP is allowed only for a loopback development endpoint",
    );
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new RuntimeError(
      "PROVIDER_BASE_URL_UNSAFE",
      "provider base URL must not contain credentials, query parameters or fragments",
    );
  }
  return url.toString().replace(/\/$/, "");
}

export function loadRuntimeProviderConfiguration(
  source: NodeJS.ProcessEnv = process.env,
): RuntimeProviderConfiguration {
  const kind = providerKind(source.VFBIZ_AGENT_RUNTIME_PROVIDER);
  return Object.freeze({
    kind,
    apiKey: source.VFBIZ_AGENT_RUNTIME_API_KEY?.trim() || source.OPENAI_API_KEY?.trim() || null,
    baseUrl: normalizedBaseUrl(source.VFBIZ_AGENT_RUNTIME_BASE_URL),
    apiMode: providerApiMode(source.VFBIZ_AGENT_RUNTIME_API_MODE, kind),
  });
}

export function assertRuntimeProviderReady(
  configuration: RuntimeProviderConfiguration,
): void {
  if (!configuration.apiKey) {
    throw new RuntimeError(
      "PROVIDER_KEY_MISSING",
      "VFBIZ_AGENT_RUNTIME_API_KEY (or legacy OPENAI_API_KEY) is required for live execution",
    );
  }
  if (configuration.kind === "openai-compatible" && !configuration.baseUrl) {
    throw new RuntimeError(
      "PROVIDER_BASE_URL_MISSING",
      "VFBIZ_AGENT_RUNTIME_BASE_URL is required for an OpenAI-compatible provider",
    );
  }
}
