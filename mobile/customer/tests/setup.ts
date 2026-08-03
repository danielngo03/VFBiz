jest.mock("expo-constants", () => ({
  expoConfig: {
    extra: {
      customerEnvironment: "development",
      apiBaseUrl: "http://localhost:3000",
      oidcIssuer: "http://localhost:8080/realms/vfbiz-customer",
      oidcClientId: "vfbiz-customer-mobile",
      redirectScheme: "com.vfbiz.customer.dev",
      market: "VN",
      assistantEnabled: false,
    },
  },
}));
