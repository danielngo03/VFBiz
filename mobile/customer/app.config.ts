import type { ConfigContext, ExpoConfig } from "expo/config";

type CustomerEnvironment = "development" | "preview" | "production";

const environmentConfig: Record<
  CustomerEnvironment,
  {
    nameSuffix: string;
    bundleIdentifier: string;
    packageName: string;
    redirectScheme: string;
  }
> = {
  development: {
    nameSuffix: " Dev",
    bundleIdentifier: "com.vfbiz.customer.dev",
    packageName: "com.vfbiz.customer.dev",
    redirectScheme: "com.vfbiz.customer.dev",
  },
  preview: {
    nameSuffix: " Preview",
    bundleIdentifier: "com.vfbiz.customer.preview",
    packageName: "com.vfbiz.customer.preview",
    redirectScheme: "com.vfbiz.customer.preview",
  },
  production: {
    nameSuffix: "",
    bundleIdentifier: "com.vfbiz.customer",
    packageName: "com.vfbiz.customer",
    redirectScheme: "com.vfbiz.customer",
  },
};

function customerEnvironment(value: string | undefined): CustomerEnvironment {
  const candidate = value ?? "development";
  if (!(candidate in environmentConfig))
    throw new Error(`Unsupported VFBIZ_CUSTOMER_ENV: ${candidate}`);
  return candidate as CustomerEnvironment;
}

function publicUrl(
  name: string,
  developmentFallback: string,
  environment: CustomerEnvironment,
): string {
  const value =
    process.env[name] ??
    (environment === "development" ? developmentFallback : undefined);
  if (!value) throw new Error(`${name} is required outside development.`);
  const parsed = new URL(value);
  if (environment !== "development" && parsed.protocol !== "https:")
    throw new Error(`${name} must use HTTPS outside development.`);
  return parsed.toString().replace(/\/$/u, "");
}

export default ({ config }: ConfigContext): ExpoConfig => {
  const environment = customerEnvironment(process.env.VFBIZ_CUSTOMER_ENV);
  const identifiers = environmentConfig[environment];
  const apiBaseUrl = publicUrl(
    "EXPO_PUBLIC_VFBIZ_API_BASE_URL",
    "http://localhost:3000",
    environment,
  );
  const oidcIssuer = publicUrl(
    "EXPO_PUBLIC_VFBIZ_OIDC_ISSUER",
    "http://localhost:8080/realms/vfbiz-customer",
    environment,
  );
  const oidcClientId =
    process.env.EXPO_PUBLIC_VFBIZ_OIDC_CLIENT_ID ??
    (environment === "development" ? "vfbiz-customer-mobile" : undefined);
  if (!oidcClientId)
    throw new Error("EXPO_PUBLIC_VFBIZ_OIDC_CLIENT_ID is required.");

  return {
    ...config,
    name: `VFBiz Customer${identifiers.nameSuffix}`,
    slug: "vfbiz-customer",
    ...(process.env.EXPO_PUBLIC_EAS_OWNER
      ? { owner: process.env.EXPO_PUBLIC_EAS_OWNER }
      : {}),
    version: "0.1.0",
    orientation: "portrait",
    scheme: identifiers.redirectScheme,
    userInterfaceStyle: "automatic",
    platforms: ["ios", "android"],
    ios: {
      supportsTablet: true,
      bundleIdentifier: identifiers.bundleIdentifier,
      config: { usesNonExemptEncryption: false },
      infoPlist: {
        NSAppTransportSecurity: { NSAllowsArbitraryLoads: false },
      },
    },
    android: {
      package: identifiers.packageName,
      allowBackup: false,
      adaptiveIcon: {
        backgroundColor: "#F7F9FC",
      },
      blockedPermissions: [
        "android.permission.CAMERA",
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.ACCESS_COARSE_LOCATION",
        "android.permission.READ_CONTACTS",
        "android.permission.BLUETOOTH_CONNECT",
        "android.permission.POST_NOTIFICATIONS",
        "android.permission.SYSTEM_ALERT_WINDOW",
        "android.permission.READ_EXTERNAL_STORAGE",
        "android.permission.WRITE_EXTERNAL_STORAGE",
      ],
    },
    plugins: [
      "expo-router",
      [
        "expo-secure-store",
        {
          configureAndroidBackup: true,
          faceIDPermission:
            "Cho phép VFBiz bảo vệ thông tin đăng nhập trên thiết bị này.",
        },
      ],
    ],
    experiments: { typedRoutes: true },
    updates: {
      enabled: false,
      checkAutomatically: "NEVER",
    },
    runtimeVersion: { policy: "fingerprint" },
    extra: {
      customerEnvironment: environment,
      apiBaseUrl,
      oidcIssuer,
      oidcClientId,
      redirectScheme: identifiers.redirectScheme,
      market: process.env.EXPO_PUBLIC_VFBIZ_MARKET ?? "VN",
      assistantEnabled: false,
      eas: process.env.EXPO_PUBLIC_EAS_PROJECT_ID
        ? { projectId: process.env.EXPO_PUBLIC_EAS_PROJECT_ID }
        : undefined,
    },
  };
};
