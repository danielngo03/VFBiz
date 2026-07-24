import { timingSafeEqual } from "node:crypto";
import { privateJson } from "@/platform/api/http-responses";
import { readCustomerPortalEnvironment } from "@/platform/config/environment";
import { drainProviderRevocations } from "@/platform/session/provider-revocation-reconciler";

function hasWorkerCredential(request: Request): boolean {
  const configured =
    readCustomerPortalEnvironment().CUSTOMER_PROVIDER_RECONCILIATION_TOKEN;
  if (configured === undefined) return false;
  const supplied = request.headers.get("authorization");
  if (!supplied?.startsWith("Bearer ")) return false;
  const expectedBuffer = Buffer.from(configured);
  const suppliedBuffer = Buffer.from(supplied.slice("Bearer ".length));
  return (
    expectedBuffer.byteLength === suppliedBuffer.byteLength &&
    timingSafeEqual(expectedBuffer, suppliedBuffer)
  );
}

export async function POST(request: Request) {
  const environment = readCustomerPortalEnvironment();
  if (environment.CUSTOMER_PROVIDER_RECONCILIATION_TOKEN === undefined) {
    return privateJson(
      { error: "reconciliation_worker_not_configured" },
      { status: 503 },
    );
  }
  if (!hasWorkerCredential(request)) {
    return privateJson({ error: "invalid_worker_credential" }, { status: 401 });
  }
  return privateJson(await drainProviderRevocations());
}
