import { privateJson } from "@/platform/api/http-responses";
import { currentCustomerSession } from "@/platform/session/current-session";

export async function GET() {
  const active = await currentCustomerSession();
  if (active === null) {
    return privateJson({ error: "session_required" }, { status: 401 });
  }
  return privateJson({
    csrfToken: active.record.session.csrfToken,
    emailVerified: active.record.session.emailVerified,
    mfaSatisfied: active.record.session.mfaSatisfied,
  });
}
