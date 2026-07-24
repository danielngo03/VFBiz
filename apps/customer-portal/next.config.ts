import type { NextConfig } from "next";

export function parseServerActionAllowedOrigins(value: string): string[] {
  return value
    .split(",")
    .map((origin) => origin.trim())
    .filter((origin) => origin.length > 0)
    .map((origin) => {
      if (
        /[\s/*@?#]/u.test(origin) ||
        !/^[a-z0-9.-]+(?::[0-9]{1,5})?$/iu.test(origin)
      ) {
        throw new Error(
          `Invalid CUSTOMER_SERVER_ACTION_ALLOWED_ORIGINS entry: ${origin}`,
        );
      }
      const parsed = new URL(`https://${origin}`);
      if (
        parsed.host.toLowerCase() !== origin.toLowerCase() ||
        parsed.hostname.startsWith(".") ||
        parsed.hostname.endsWith(".") ||
        parsed.hostname.includes("..")
      ) {
        throw new Error(
          `Invalid CUSTOMER_SERVER_ACTION_ALLOWED_ORIGINS entry: ${origin}`,
        );
      }
      return parsed.host.toLowerCase();
    });
}

const extraServerActionOrigins = parseServerActionAllowedOrigins(
  process.env.CUSTOMER_SERVER_ACTION_ALLOWED_ORIGINS ?? "",
);

const securityHeaders = [
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
];

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  poweredByHeader: false,
  reactStrictMode: true,
  experimental: {
    serverActions: {
      bodySizeLimit: "256kb",
      ...(extraServerActionOrigins.length === 0
        ? {}
        : { allowedOrigins: extraServerActionOrigins }),
    },
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
