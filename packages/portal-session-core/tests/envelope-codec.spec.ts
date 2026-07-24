import { randomBytes } from "node:crypto";
import { describe, expect, it } from "vitest";
import { EnvelopeCodec } from "../src/crypto/envelope-codec";

const primary = randomBytes(32);
const secondary = randomBytes(32);
const context = {
  namespace: "test",
  recordId: "session-1",
  recordType: "session",
};

describe("EnvelopeCodec", () => {
  it("pins the active key id and authenticates record context", () => {
    const codec = new EnvelopeCodec({
      activeKeyId: "primary",
      key: (id) => ({ primary, secondary })[id],
    });
    const sealed = codec.seal({ token: "sensitive" }, context);
    expect(sealed.startsWith("v1.primary.")).toBe(true);
    expect(codec.open<{ token: string }>(sealed, context).value.token).toBe(
      "sensitive",
    );
    expect(() =>
      codec.open(sealed, { ...context, recordId: "another-session" }),
    ).toThrow();
  });

  it("reads records encrypted by a retained rotation key", () => {
    const oldCodec = new EnvelopeCodec({
      activeKeyId: "secondary",
      key: (id) => ({ primary, secondary })[id],
    });
    const currentCodec = new EnvelopeCodec({
      activeKeyId: "primary",
      key: (id) => ({ primary, secondary })[id],
    });
    const sealed = oldCodec.seal({ value: 1 }, context);
    expect(currentCodec.open<{ value: number }>(sealed, context).value.value).toBe(
      1,
    );
  });

  it("fails closed for an unknown key id or tampered ciphertext", () => {
    const codec = new EnvelopeCodec({
      activeKeyId: "primary",
      key: (id) => (id === "primary" ? primary : undefined),
    });
    const sealed = codec.seal({ value: 1 }, context);
    expect(() => codec.open(sealed.replace(".primary.", ".missing."), context)).toThrow(
      /Unknown vault key/u,
    );
    expect(() => codec.open(`${sealed.slice(0, -1)}A`, context)).toThrow();
  });
});
