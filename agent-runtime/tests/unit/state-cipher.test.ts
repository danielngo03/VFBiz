import { describe, expect, it } from "vitest";
import { StateCipher } from "../../src/adapters/persistence/sqlite/state-cipher.js";
import { testStateKey } from "../helpers.js";

describe("checkpoint cipher", () => {
  it("authenticates and decrypts serialized state", () => {
    const cipher = new StateCipher(testStateKey);
    const encrypted = cipher.encrypt('{"prompt":"synthetic"}');
    expect(encrypted.ciphertext).not.toContain("synthetic");
    expect(cipher.decrypt(encrypted.ciphertext)).toBe('{"prompt":"synthetic"}');
    const parts = encrypted.ciphertext.split(":");
    parts[2] = `${parts[2]?.startsWith("A") ? "B" : "A"}${parts[2]?.slice(1) ?? ""}`;
    expect(() => cipher.decrypt(parts.join(":"))).toThrow(/authentication/);
  });

  it("requires an external 32-byte key", () => {
    expect(() => new StateCipher("")).toThrow(/required/);
    expect(() => new StateCipher(Buffer.from("short").toString("base64"))).toThrow(/32-byte/);
  });
});
