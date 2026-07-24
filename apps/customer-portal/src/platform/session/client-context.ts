import "server-only";
import { readCustomerPortalEnvironment } from "@/platform/config/environment";

function browser(value: string): string {
  if (/Edg\//iu.test(value)) return "Edge";
  if (/Chrome\//iu.test(value)) return "Chrome";
  if (/Firefox\//iu.test(value)) return "Firefox";
  if (/Safari\//iu.test(value)) return "Safari";
  return "Browser";
}

function platform(value: string): string {
  if (/iPhone|iPad/iu.test(value)) return "iOS";
  if (/Android/iu.test(value)) return "Android";
  if (/Windows/iu.test(value)) return "Windows";
  if (/Macintosh|Mac OS X/iu.test(value)) return "macOS";
  if (/Linux/iu.test(value)) return "Linux";
  return "Unknown device";
}

function networkPrefix(value: string | null): string | null {
  if (value === null) return null;
  const address = value.split(",")[0]?.trim() ?? "";
  const ipv4 = address.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.\d{1,3}$/u);
  if (ipv4 !== null) {
    const octets = ipv4.slice(1).map(Number);
    if (octets.every((octet) => octet >= 0 && octet <= 255)) {
      return `${octets.join(".")}.0/24`;
    }
  }
  if (address.includes(":")) {
    const groups = address.split(":").filter(Boolean).slice(0, 4);
    return groups.length === 0 ? null : `${groups.join(":")}::/64`;
  }
  return null;
}

export function customerClientContext(request: Request) {
  const environment = readCustomerPortalEnvironment();
  const rawUserAgent = request.headers.get("user-agent");
  const userAgent =
    rawUserAgent?.replaceAll(/[\u0000-\u001f\u007f]/gu, "").slice(0, 255) ??
    null;
  const forwarded = environment.CUSTOMER_TRUST_PROXY_HEADERS
    ? request.headers.get("x-forwarded-for")
    : null;
  return {
    deviceLabel:
      userAgent === null
        ? null
        : `${browser(userAgent)} on ${platform(userAgent)}`,
    networkHint: networkPrefix(forwarded),
    userAgentSummary: userAgent,
  };
}
