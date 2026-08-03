import { cacheNamespace } from "../../src/platform/storage/cache-namespace";

test("isolates cache by environment issuer subject market and schema", () => {
  const namespace = cacheNamespace({
    app: "customer",
    environment: "preview",
    issuer: "https://identity.example.test/realms/customer",
    subject: "subject-test-001",
    market: "vn",
  });
  expect(namespace).toContain("customer:preview:");
  expect(namespace).toContain("subject-test-001:VN:1");
});
