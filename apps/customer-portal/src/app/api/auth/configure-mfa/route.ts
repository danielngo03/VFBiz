import { startCustomerAuthorization } from "@/platform/auth/start-authorization";
import { privateJson } from "@/platform/api/http-responses";
import { currentCustomerSession } from "@/platform/session/current-session";

export async function GET(request: Request) {
  if ((await currentCustomerSession()) === null) {
    return privateJson({ error: "session_required" }, { status: 401 });
  }
  return startCustomerAuthorization(request, "configure-mfa");
}
