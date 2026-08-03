import { describe, expect, it } from "vitest";
import { loadRuntimeEnvironment } from "../../src/config/env.js";
import {
  assertRuntimeProviderReady,
  loadRuntimeProviderConfiguration,
} from "../../src/config/provider.js";

describe("runtime provider configuration", () => {
  it("uses OpenAI Responses defaults and accepts the legacy key", () => {
    expect(loadRuntimeProviderConfiguration({ OPENAI_API_KEY: "legacy-key" })).toEqual({
      kind: "openai",
      apiKey: "legacy-key",
      baseUrl: null,
      apiMode: "responses",
    });
  });

  it("configures an OpenAI-compatible Chat Completions endpoint", () => {
    const configuration = loadRuntimeProviderConfiguration({
      VFBIZ_AGENT_RUNTIME_PROVIDER: "openai-compatible",
      VFBIZ_AGENT_RUNTIME_API_KEY: "provider-key",
      VFBIZ_AGENT_RUNTIME_BASE_URL: "https://provider.example/v1/",
    });
    expect(configuration).toEqual({
      kind: "openai-compatible",
      apiKey: "provider-key",
      baseUrl: "https://provider.example/v1",
      apiMode: "chat-completions",
    });
    expect(() => assertRuntimeProviderReady(configuration)).not.toThrow();
  });

  it("requires a base URL for a compatible provider", () => {
    const configuration = loadRuntimeProviderConfiguration({
      VFBIZ_AGENT_RUNTIME_PROVIDER: "openai-compatible",
      VFBIZ_AGENT_RUNTIME_API_KEY: "provider-key",
    });
    expect(() => assertRuntimeProviderReady(configuration)).toThrowError(/BASE_URL/);
  });

  it("rejects insecure remote endpoints and credentials in URLs", () => {
    expect(() => loadRuntimeProviderConfiguration({
      VFBIZ_AGENT_RUNTIME_BASE_URL: "http://provider.example/v1",
    })).toThrowError(/HTTPS/);
    expect(() => loadRuntimeProviderConfiguration({
      VFBIZ_AGENT_RUNTIME_BASE_URL: "https://user:secret@provider.example/v1",
    })).toThrowError(/credentials/);
  });

  it("allows loopback HTTP for a local compatible gateway", () => {
    expect(loadRuntimeProviderConfiguration({
      VFBIZ_AGENT_RUNTIME_PROVIDER: "openai-compatible",
      VFBIZ_AGENT_RUNTIME_API_KEY: "local-key",
      VFBIZ_AGENT_RUNTIME_BASE_URL: "http://127.0.0.1:4000/v1",
    }).baseUrl).toBe("http://127.0.0.1:4000/v1");
  });

  it("supports the new live flag and the legacy OpenAI flag", () => {
    expect(loadRuntimeEnvironment({ VFBIZ_AGENT_RUNTIME_LIVE_ENABLED: "true" }).liveProviderEnabled)
      .toBe(true);
    expect(loadRuntimeEnvironment({ VFBIZ_AGENT_RUNTIME_OPENAI_ENABLED: "true" }).liveProviderEnabled)
      .toBe(true);
  });
});
