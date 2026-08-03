import { spawnSync } from "node:child_process";

const result = spawnSync("npx", ["expo", "config", "--type", "introspect", "--json"], {
  cwd: process.cwd(),
  encoding: "utf8",
  env: {
    ...process.env,
    VFBIZ_CUSTOMER_ENV: "production",
    EXPO_PUBLIC_VFBIZ_API_BASE_URL: "https://api.customer.invalid",
    EXPO_PUBLIC_VFBIZ_OIDC_ISSUER: "https://identity.customer.invalid/realms/customer",
    EXPO_PUBLIC_VFBIZ_OIDC_CLIENT_ID: "customer-mobile-release-check",
  },
});
if (result.status !== 0) throw new Error(result.stderr || "Expo introspection failed.");
const config = JSON.parse(result.stdout);
const application = config._internal.modResults.android.manifest.manifest.application[0].$;
if (config.scheme !== "com.vfbiz.customer") throw new Error("Production callback scheme drifted.");
if (application["android:allowBackup"] !== "false") throw new Error("Android backup must remain disabled.");
if (config.ios.infoPlist.NSAppTransportSecurity?.NSAllowsArbitraryLoads !== false)
  throw new Error("Production ATS must reject arbitrary loads.");

const forbidden = new Set([
  "android.permission.CAMERA",
  "android.permission.ACCESS_FINE_LOCATION",
  "android.permission.ACCESS_COARSE_LOCATION",
  "android.permission.READ_CONTACTS",
  "android.permission.BLUETOOTH_CONNECT",
  "android.permission.POST_NOTIFICATIONS",
  "android.permission.SYSTEM_ALERT_WINDOW",
  "android.permission.READ_EXTERNAL_STORAGE",
  "android.permission.WRITE_EXTERNAL_STORAGE",
]);
const declarations = config._internal.modResults.android.manifest.manifest["uses-permission"] ?? [];
for (const declaration of declarations) {
  const permission = declaration.$?.["android:name"];
  if (forbidden.has(permission) && declaration.$?.["tools:node"] !== "remove")
    throw new Error(`Forbidden production permission remains active: ${permission}`);
}
console.log("Customer production native config is fail-closed.");
