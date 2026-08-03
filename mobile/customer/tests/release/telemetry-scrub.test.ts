import { scrubTelemetry } from "../../src/platform/observability/logger";

test("scrubs nested credentials and customer identifiers", () => {
  expect(
    scrubTelemetry({ accessToken: "secret", nested: { vin: "VIN", safe: "ok" } }),
  ).toEqual({ accessToken: "[REDACTED]", nested: { vin: "[REDACTED]", safe: "ok" } });
});
