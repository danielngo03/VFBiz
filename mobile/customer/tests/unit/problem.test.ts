import { problemFromResponse } from "../../src/platform/api/problem";

test("maps RFC Problem Details and correlation id", () => {
  expect(
    problemFromResponse(
      412,
      { type: "urn:vfbiz:conflict", title: "Version conflict", detail: "Refresh" },
      "corr-001",
    ),
  ).toEqual({
    type: "urn:vfbiz:conflict",
    title: "Version conflict",
    detail: "Refresh",
    status: 412,
    correlationId: "corr-001",
  });
});
