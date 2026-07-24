import { startCustomerAuthorization } from "@/platform/auth/start-authorization";

export async function GET(request: Request) {
  return startCustomerAuthorization(request, "register");
}
