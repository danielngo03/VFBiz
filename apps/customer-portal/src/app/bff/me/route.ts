import { customerApiGet } from "@/platform/api/customer-api";
import { secureUpstreamResponse } from "@/platform/api/http-responses";

export async function GET() {
  const upstream = await customerApiGet("/api/v1/me");
  return secureUpstreamResponse(upstream);
}
