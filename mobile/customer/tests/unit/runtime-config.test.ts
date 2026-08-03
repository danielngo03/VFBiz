import { runtimeConfigFromExtra } from "../../src/platform/config/runtime-config";

test("requires HTTPS for production public endpoints", () => {
  expect(() =>
    runtimeConfigFromExtra({
      customerEnvironment: "production",
      apiBaseUrl: "http://api.example.test",
      oidcIssuer: "https://identity.example.test/realms/customer",
      oidcClientId: "customer-mobile",
      redirectScheme: "com.vfbiz.customer",
      market: "vn",
    }),
  ).toThrow("apiBaseUrl must use HTTPS");
});

test("normalizes public runtime config", () => {
  expect(
    runtimeConfigFromExtra({
      customerEnvironment: "preview",
      apiBaseUrl: "https://api.example.test/",
      oidcIssuer: "https://identity.example.test/realms/customer/",
      oidcClientId: "customer-mobile",
      redirectScheme: "com.vfbiz.customer.preview",
      market: "vn",
      assistantEnabled: false,
    }),
  ).toMatchObject({
    environment: "preview",
    apiBaseUrl: "https://api.example.test",
    market: "VN",
    assistantEnabled: false,
  });
});
